import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('WILLY_SIMULATE','1')
import numpy as np
import pytest
pytest.importorskip("cv2")   # on the rover; the Windows test venv has no OpenCV

# 2026-10-13: the detector was fed BGR, squashed frames; a red ball scored nothing.

def test_letterbox_keeps_aspect_swaps_to_rgb_and_maps_back():
    import vision
    f=np.zeros((720,1280,4),np.uint8); f[...,2]=200            # B,G,R,X bytes: R=200 -> red
    img,(sx,sy,px,py)=vision._letterbox_rgb(f,(640,640))
    assert img.shape==(640,640,3)
    assert img[320,320,0]==200 and img[320,320,2]==0           # red ends up in channel 0 (RGB)
    assert py==140 and px==0 and img[10,10,0]==114             # grey bars top/bottom
    # a point at frame (1280*0.6, 720*0.9) round-trips through model coordinates
    X,Y=768,648; mx,my=X*sx+px,Y*sy+py
    assert abs((mx-px)/sx-X)<1e-6 and abs((my-py)/sy-Y)<1e-6
