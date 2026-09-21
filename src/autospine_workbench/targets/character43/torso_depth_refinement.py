"""Opt-in torso-plane checks with observed fingertips and weighted intervals."""
from .cloth_depth_plane import at
from .hand_depth_observation import observe
from .hand_mesh_axis import infer
from .weighted_depth_interval import build
from .mesh_depth_proxy import overlap_support
from ..spine43.seam_raster import texture

PROFILE='torso-plane-hand-interval-held-order-v1-experiment'


class Checker:
    def __init__(self,probe,sampler,*,plane_provider=None,pixelwise=False,sleeve_helpers=None):
        self.probe,self.sampler=probe,sampler
        self.plane_provider=plane_provider or at
        self.pixelwise=pixelwise
        self.axes={}; self.models={}
        self.sleeve_helpers=sleeve_helpers

    def check(self,arm,body,time,source_tick,*,on_triangle=None):
        probe=self.probe
        if not probe.pair(arm,body,time)['overlap_pixels']:
            return dict(status='no_overlap',time=time)
        slot=probe.slots[arm]
        mesh=probe.document['skins'][0]['attachments'][arm][slot['attachment']]
        if arm not in self.axes:
            self.axes[arm]=infer(probe.document,mesh,texture(probe.files[
                'images/'+mesh.get('path',slot['attachment'])+'.png']))
        key=(time,source_tick)
        if key not in self.models:
            segments=self.sampler(source_tick)
            hands=observe(self.sampler,source_tick,full_hand=True)
            segments.update(hands['segments'])
            plane=self.plane_provider(probe.document,probe.animation,time,self.sampler,source_tick)
            self.models[key]=(segments,hands,plane)
        segments,hands,plane=self.models[key]
        lengths={n:v['length'] for n,v in self.axes[arm]['axes'].items() if n in hands['segments']}
        intervals=build(probe.document,mesh,segments,axis_lengths=lengths)
        if self.sleeve_helpers:
            from .sleeve_depth_intervals import at as sleeve_intervals
            intervals=sleeve_intervals(probe,self.sampler,source_tick,arm,time,segments,self.sleeve_helpers,axis_lengths=lengths)
        result=overlap_support(probe,arm,body,time,segments,endpoint_caps=True,
            reference_plane=plane['coefficients'],axis_lengths=lengths,depth_intervals=intervals['intervals'],pixelwise=self.pixelwise,on_triangle=on_triangle)
        if self.sleeve_helpers:
            result['sleeve_depth_model']={k:v for k,v in intervals.items() if k!='intervals'}
        return dict(result,reference_plane_evidence=plane)
