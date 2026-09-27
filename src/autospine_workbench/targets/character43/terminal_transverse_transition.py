"""Bind-space smooth taper of transverse compensation into terminal joints."""
import math


def gains(document, slot, fraction):
    if not math.isfinite(fraction) or not 0<fraction<=1:raise ValueError('terminal_transition_fraction')
    bones=document['bones'];by_name={b['name']:b for b in bones};lengths={}
    for side in ('l','r'):
        for parent,child in (('calf_'+side,'foot_'+side),('forearm_'+side,'hand_'+side)):
            if parent not in by_name or child not in by_name:continue
            tip=by_name[child];length=tip.get('x',0)
            if tip.get('parent')!=parent or not math.isfinite(length) or length<=0 or abs(tip.get('y',0))>1e-6*length:
                raise ValueError('terminal_transition_nonaxial_chain')
            lengths[parent]=length
    data=document['skins'][0]['attachments'][slot][slot]['vertices'];cursor=0;result=[]
    while cursor<len(data):
        count=data[cursor];cursor+=1
        for _ in range(count):
            index,x,_,_=data[cursor:cursor+4];cursor+=4;name=bones[index]['name']
            if name in ('foot_l','foot_r','hand_l','hand_r'):gain=0.
            elif name in lengths:
                u=max(0.,min(1.,(lengths[name]-x)/(fraction*lengths[name])))
                gain=u*u*(3-2*u)
            else:gain=1.
            result.append(gain)
    return result
