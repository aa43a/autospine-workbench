"""One explicit routing policy for arm/body and arm/limb depth evidence."""
from .torso_depth_refinement import Checker
from .hand_depth_observation import observe
from .hand_mesh_axis import infer
from .weighted_depth_interval import build
from .mesh_pair_depth import compare
from ..spine43.seam_raster import texture


class SurfaceChecker:
    def __init__(self,probe,sampler,inventory,*,plane_provider=None,source_axes=None,allow_garment_plane=True):
        self.probe,self.sampler=probe,sampler
        self.plane=Checker(probe,sampler,pixelwise=True,plane_provider=plane_provider)
        self.roles={r['slot']:r['role'] for r in inventory['surfaces']};self.models={}
        self.axes=dict(source_axes or {});self.plane.axes.update(self.axes)
        self.allow_garment_plane=allow_garment_plane

    def check(self,arm,body,time,source_tick,*,on_triangle=None):
        probe=self.probe
        if not probe.pair(arm,body,time)['overlap_pixels']:return dict(status='no_overlap',time=time)
        role=self.roles[body]
        if role=='garment_plane_candidate' and not self.allow_garment_plane:
            raise ValueError('surface_depth_model_unavailable:garment_requires_declared_surface')
        if role in ('torso','garment_plane_candidate'):
            return self.plane.check(arm,body,time,source_tick,on_triangle=on_triangle)
        if not role.startswith(('arm.','leg.')):
            raise ValueError('surface_depth_model_unavailable:'+role)
        key=(time,source_tick)
        if key not in self.models:
            segments=self.sampler(source_tick);hands=observe(self.sampler,source_tick,full_hand=True)
            segments.update(hands['segments']);segments.update(self.sampler.leg_segments(source_tick))
            self.models[key]=segments,hands
        segments,hands=self.models[key]
        def intervals(name,kind):
            slot=probe.slots[name];mesh=probe.document['skins'][0]['attachments'][name][slot['attachment']]
            lengths={}
            if kind=='arm':
                if name not in self.axes:
                    self.axes[name]=infer(probe.document,mesh,texture(probe.files['images/'+mesh.get('path',slot['attachment'])+'.png']))
                lengths={n:v['length'] for n,v in self.axes[name]['axes'].items() if n in hands['segments']}
            return build(probe.document,mesh,segments,axis_lengths=lengths,chain_kind=kind)['intervals']
        return compare(probe,arm,body,time,intervals(arm,'arm'),intervals(body,role.split('.')[0]),on_triangle=on_triangle)
