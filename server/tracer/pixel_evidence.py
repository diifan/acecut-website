"""Native TracerPixelEvidence gates, applied only to model-backed observations.

Uses the same 640x360 image plane, 7x7 evidence patches, 18-frame
history and +/-3-frame stationary gate as AceCut. Does not create tracks.
"""
import cv2
import numpy as np

def refine(frames, observations, mapping):
    mx,my,mw,mh=mapping
    history=[];previous=None;rows=[]
    for i,frame in enumerate(frames):
        rgb=frame.astype(np.float64)
        gray=np.floor(rgb[:,:,0]*.299+rgb[:,:,1]*.587+rgb[:,:,2]*.114+.5).astype(np.uint8)
        diff=np.zeros_like(gray) if previous is None else np.abs(gray.astype(np.int16)-previous.astype(np.int16)).astype(np.uint8)
        hi=rgb.max(axis=2);lo=rgb.min(axis=2);delta=hi-lo;den=np.where(delta>0,delta,1)
        r,g,b=rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
        hue=np.where(hi==r,60*(g-b)/den,np.where(hi==g,60*((b-r)/den+2),60*((r-g)/den+4)))
        yellow=(hi>=100)&(delta>=hi*65/255)&(delta>0)&(hue>=40)&(hue<=96)
        moving=(yellow&(diff>18)).astype(np.uint8)
        n,labels,stats,centers=cv2.connectedComponentsWithStats(moving,8)
        blobs=[centers[j] for j in range(1,n) if 2<=stats[j,4]<=45 and stats[j,2]<=14 and stats[j,3]<=14]
        p=observations.get(i);e=None
        if p is not None:
            x=(p['x']*mw+mx)*640;y=(p['y']*mh+my)*360
            ix=min(639,max(0,int(np.floor(x+.5))));iy=min(359,max(0,int(np.floor(y+.5))))
            sl=np.s_[max(0,iy-3):min(360,iy+4),max(0,ix-3):min(640,ix+4)]
            e=dict(p=p,x=x,y=y,mean=float(diff[sl].mean()),maximum=int(diff[sl].max()),color=int(yellow[sl].sum()),moving=int((yellow[sl]&(diff[sl]>15)).sum()),persistent=sum(int(m[sl].sum())>=2 for m in history),history=len(history))
        rows.append((e,blobs));previous=gray;history.append(yellow)
        if len(history)>18:history.pop(0)
    result={}
    for i,(e,blobs) in enumerate(rows):
        if e is None:continue
        adjacent=[a for a,_ in rows[max(0,i-3):i+4] if a is not None and np.hypot(a['x']-e['x'],a['y']-e['y'])<=5]
        stationary=sum(a['color']>=2 and a['moving']==0 and a['mean']<9 and a['maximum']<45 for a in adjacent)
        moving=any(a['moving']>=3 or a['mean']>15 for a in adjacent)
        if (e['history']>=15 and e['persistent']>=12 and e['mean']<10 and e['maximum']<50) or (stationary>=3 and not moving):continue
        p=dict(e['p']);near=[b for b in blobs if np.hypot(b[0]-e['x'],b[1]-e['y'])<=6]
        if near:
            b=min(near,key=lambda b:np.hypot(b[0]-e['x'],b[1]-e['y']))
            p['x']=(.35*e['x']/640+.65*b[0]/640-mx)/mw
            p['y']=(.35*e['y']/360+.65*b[1]/360-my)/mh
        result[i]=p
    return result
