"""Deterministic artistic wind in a fixed world XY plane (not SI aerodynamics)."""
from bisect import bisect_right
from copy import deepcopy
import math

SCHEMA = 'autospine.wind/v1'
RESPONSE_PROFILE = 'bounded-equilibrium-v2'


def defaults():
    return dict(schema=SCHEMA, enabled=False, strength=25., direction=0., gust=.25,
                frequency=.5, seed=0, keys=[])


def normalize(value, duration):
    result = defaults()
    if not isinstance(value, dict) or set(value)-set(result)-{'response_profile'}:
        raise ValueError('joint_wind_config')
    result.update(deepcopy(value))
    if result['schema'] != SCHEMA or type(result['enabled']) is not bool:
        raise ValueError('joint_wind_config')
    if 'response_profile' in result and result['response_profile'] not in ('legacy-angular-v1', RESPONSE_PROFILE):
        raise ValueError('joint_wind_response_profile')
    for key, lo, hi in [('strength', 0, 100), ('direction', 0, 360), ('gust', 0, 1), ('frequency', 0, 4)]:
        v = result[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError('joint_wind_parameter_'+key)
        result[key] = float(v)
    if type(result['seed']) is not int or not 0 <= result['seed'] <= 2147483647:
        raise ValueError('joint_wind_seed')
    if not isinstance(result['keys'], list) or len(result['keys']) > 128:
        raise ValueError('joint_wind_keys')
    last = stored = -1.
    import struct
    for key in result['keys']:
        if not isinstance(key, dict) or set(key) != {'time', 'strength', 'direction'}:
            raise ValueError('joint_wind_key_fields')
        for name, lo, hi in [('time', 0, duration), ('strength', 0, 100), ('direction', 0, 360)]:
            v = key[name]
            if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
                raise ValueError('joint_wind_key_'+name)
        f32 = struct.unpack('<f', struct.pack('<f', key['time']))[0]
        if key['time'] <= last or f32 <= stored:
            raise ValueError('joint_wind_key_time')
        last, stored = key['time'], f32
    return result


def parameters(config, time):
    keys = config['keys']
    if not keys:
        return config['strength'], config['direction']
    i = bisect_right([k['time'] for k in keys], time)-1
    if i < 0:
        return keys[0]['strength'], keys[0]['direction']
    if i >= len(keys)-1:
        return keys[-1]['strength'], keys[-1]['direction']
    a, b = keys[i:i+2]; f = (time-a['time'])/(b['time']-a['time'])
    delta = (b['direction']-a['direction']+180) % 360-180
    return a['strength']+(b['strength']-a['strength'])*f, a['direction']+delta*f


def vectors(config, times, *, loop=False):
    """Seeded harmonics modulate external forcing, never an output angle."""
    config = normalize(config, times[-1])
    frequency = config['frequency']
    if loop and frequency:
        frequency = max(1, math.floor(frequency*times[-1]+.5))/times[-1]
    phase = (config['seed'] % 65536)/65536*2*math.pi
    values = []
    for t in times:
        strength, direction = parameters(config, t)
        pulse = .65*math.sin(2*math.pi*frequency*t+phase)+.35*math.sin(4*math.pi*frequency*t+phase*.73)
        speed = strength/100*(1+config['gust']*pulse if frequency else 1)
        force = speed*abs(speed) if config['enabled'] else 0.
        angle = math.radians(direction)
        values.append((force*math.cos(angle), force*math.sin(angle)))
    compatible = math.dist(values[0], values[-1]) <= 1e-8
    return values, dict(profile=SCHEMA, enabled=config['enabled'], basis='fixed_world_xy',
        units='artistic_strength_not_metres_per_second', effective_frequency_hz=frequency,
        seed=config['seed'], endpoint_vector_error=math.dist(values[0], values[-1]),
        loop_compatible=compatible, deterministic=True, keys=len(config['keys']),
        max_vector_strength=max(math.hypot(x,y) for x,y in values),
        response_profile=config.get('response_profile', 'legacy-angular-v1'))


def angular_forces(vectors, poses, *, axis_offset=0., response=1., length=100.,
                   profile='legacy-angular-v1', stiffness=36., max_angle=4.):
    # Calibrate the external equilibrium to the chosen movement limit. The
    # legacy fixed acceleration reaches the hard angle stop at modest wind,
    # making most of the strength slider indistinguishable.
    acceleration = .9*stiffness*max_angle if profile == RESPONSE_PROFILE else 360.
    scale = acceleration*response*max(.5, min(2., math.sqrt(100/max(8., length))))
    return [scale*(math.cos(math.radians(p[2]+axis_offset))*w[1]
                  -math.sin(math.radians(p[2]+axis_offset))*w[0])
            for p,w in zip(poses,vectors,strict=True)]
