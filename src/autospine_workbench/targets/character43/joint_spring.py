"""Bounded offline secondary response, independent of playback/seek order."""
from bisect import bisect_right
import math


def grid(duration, hz=120):
    if not math.isfinite(duration) or not 0 < duration <= 120:
        raise ValueError('joint_secondary_duration')
    if hz not in (60, 120):
        raise ValueError('joint_secondary_sample_rate')
    # 60 Hz authoring keys and 120 Hz solver midpoints share an exact grid.
    # Exported microsecond durations may lie just beyond an integral tick.
    nominal = duration*60; nearest = round(nominal)
    count60 = max(1, nearest if abs(nominal-nearest) <= 1e-4 else math.ceil(nominal))
    count = count60*(2 if hz == 120 else 1)
    return [duration * i / count for i in range(count + 1)]


def interpolate(times, values, time):
    i = max(0, min(len(times) - 2, bisect_right(times, time) - 1))
    f = min(1., max(0., (time - times[i]) / (times[i + 1] - times[i])))
    return values[i] + f * (values[i + 1] - values[i])


def bake(times, values, limit=.05):
    """Nominal 60 Hz keys retain 120 Hz corners only when linear error requires it."""
    if len(times) != len(values) or len(times) < 2 or limit <= 0:
        raise ValueError('joint_secondary_key_samples')
    indices = sorted(set(range(0, len(times), 2)) | {len(times)-1})
    base_count = len(indices)
    required = set(indices)
    for first, last in zip(indices, indices[1:]):
        for index in range(first+1, last):
            fraction = (times[index]-times[first])/(times[last]-times[first])
            estimate = values[first]+fraction*(values[last]-values[first])
            if abs(values[index]-estimate) > limit:
                required.add(index)
    indices = sorted(required)
    keys = [times[i] for i in indices]; samples = [values[i] for i in indices]
    error = max(abs(v-interpolate(keys, samples, t)) for t,v in zip(times, values, strict=True))
    if error > limit+1e-10:
        raise ValueError('joint_secondary_key_approximation_limit')
    return keys, samples, dict(key_sampling='60hz_with_required_120hz_corners',
        base_key_sample_count=base_count, key_sample_count=len(keys), adaptive_key_count=len(keys)-base_count,
        key_approximation_error_deg=error, key_approximation_limit_deg=limit,
        key_peak_loss_deg=max(map(abs, values))-max(map(abs, samples)))


def _unwrap(values):
    result = [values[0]]
    for value in values[1:]:
        result.append(result[-1] + (value - result[-1] + 180) % 360 - 180)
    return result


def solve(times, poses, *, stiffness=36., damping=.85, strength=1., max_angle=4.,
          length=100., loop=False, external_forces=None, external_loop_compatible=True):
    """poses are root (world x, world y, world angle), in a FIXED camera basis.

    A damped angular spring responds to carrier rotation and lateral root
    acceleration. Gravity is a rest-direction term, not perpetual fake wind.
    The complete trajectory is baked once; evaluation never integrates time.
    """
    if len(times) < 3 or len(times) != len(poses):
        raise ValueError('joint_spring_samples')
    dt = times[1] - times[0]
    if dt <= 0 or dt > 1/60 + 1e-9 or any(abs(b-a-dt) > 1e-8 for a, b in zip(times, times[1:])):
        raise ValueError('joint_spring_fixed_step')
    if any(not math.isfinite(v) for row in poses for v in row):
        raise ValueError('joint_spring_nonfinite')
    angles = _unwrap([p[2] for p in poses]); n = len(times)
    loop_position = math.dist(poses[0][:2], poses[-1][:2])
    loop_angle = abs(angles[-1] - angles[0])
    if external_forces is not None and (len(external_forces) != n or any(not math.isfinite(v) for v in external_forces)):
        raise ValueError('joint_spring_external_forces')
    compatible = loop_position <= .25 and loop_angle <= .1 and external_loop_compatible
    periodic = bool(loop and compatible)
    forcing = []
    for i in range(n):
        a = i - 1 if i else (n - 2 if periodic else 0)
        b = i + 1 if i < n - 1 else (1 if periodic else n - 1)
        # Endpoints of nonloops are one-sided acceleration estimates.
        if not periodic and i in (0, n - 1):
            accel = 0.
        else:
            radians = math.radians(angles[i])
            dx = (poses[b][0] - 2*poses[i][0] + poses[a][0]) / (dt*dt)
            dy = (poses[b][1] - 2*poses[i][1] + poses[a][1]) / (dt*dt)
            accel = (-math.sin(radians)*dx + math.cos(radians)*dy) / max(8., length)
        target = -(angles[i] - angles[0]) * .35
        acceleration = strength*(stiffness*target - math.degrees(accel)*.35)
        if external_forces is not None:
            acceleration += strength*external_forces[i]
        forcing.append(max(-720., min(720., acceleration)))
    friction = 2*damping*math.sqrt(stiffness)
    position = velocity = 0.; history = []; values = []; velocities = []
    for cycle in range(9 if periodic else 1):
        start = position, velocity; values = [position]; velocities = [velocity]
        for force in forcing[1:]:
            velocity += (force - stiffness*position - friction*velocity)*dt
            position += velocity*dt
            if abs(position) > max_angle:
                position = math.copysign(max_angle, position)
                if position*velocity > 0: velocity = 0.
            values.append(position); velocities.append(velocity)
        error = abs(position-start[0]), abs(velocity-start[1])
        history.append(dict(position_error_deg=error[0], velocity_error_deg_s=error[1]))
        if periodic and cycle >= 1 and error[0] <= .01 and error[1] <= .1:
            break
    converged = periodic and history[-1]['position_error_deg'] <= .01 and history[-1]['velocity_error_deg_s'] <= .1
    status = ('converged' if converged else 'not_converged') if periodic else ('source_not_loopable' if loop else 'not_requested')
    return values, dict(profile='fixed-step-root-driven-angular-spring-v1', step_seconds=dt,
        sample_count=n, peak_angle_deg=max(map(abs, values)), loop_status=status,
        warmup_cycles=max(0, len(history)-1), endpoint_angle_error_deg=abs(values[-1]-values[0]),
        endpoint_velocity_error_deg_s=abs(velocities[-1]-velocities[0]),
        source_endpoint_position_error_px=loop_position, source_endpoint_angle_error_deg=loop_angle,
        history=history, bounded=True, playback_order_independent=True,
        collision_scope='angle_limit_only_no_3d_or_texture_collision')
