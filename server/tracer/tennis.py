"""112 ONNX adapter for AceCut's court/event/focus model chain.

Model outputs are observations, never a synthetic trajectory. The web adapter
keeps the native 0.975 focus confidence gate and bounds decoded video memory.
"""
import os
from pathlib import Path
import cv2
cv2.setNumThreads(2)
import numpy as np
import onnxruntime as ort

MODELS = Path(os.environ.get('ACECUT_MODELS', '/data/swi-algo/model_recovery/recovery_20261019/out'))

class Models:
    def __init__(self):
        self.sessions = {}

    def run(self, name, inputs):
        if name not in self.sessions:
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.log_severity_level = 3
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
            if os.environ.get('ACECUT_FUSED') == '1':
                options.register_custom_ops_library(str(Path(__file__).parent/'native/fixed_conv.so'))
            self.sessions[name] = ort.InferenceSession(str(MODELS / (name + '.onnx')), options,
                providers=([('CUDAExecutionProvider', {'gpu_mem_limit': 4294967296, 'arena_extend_strategy': 'kSameAsRequested', 'cudnn_conv_algo_search': 'HEURISTIC'}), 'CPUExecutionProvider'] if name.endswith('CNN') or name in ('TennisCourtNet','CourtCropNet') else ['CPUExecutionProvider']))
        session = self.sessions[name]
        types = {'tensor(float)': np.float32, 'tensor(float16)': np.float16, 'tensor(uint8)': np.uint8}
        feed = {x.name: np.asarray(inputs[x.name], dtype=types[x.type]) for x in session.get_inputs()}
        values = session.run(None, feed)
        if not all(np.isfinite(x).all() for x in values):
            raise ValueError('nonfinite_model_output')
        return dict(zip([x.name for x in session.get_outputs()], values))

def analyze(path, progress=lambda p: None):
    cap = cv2.VideoCapture(str(path),cv2.CAP_FFMPEG,[cv2.CAP_PROP_N_THREADS,2])
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not 1 <= fps <= 120:
        raise ValueError('invalid_frame_rate')
    frames = []
    mapping = (0.,0.,1.,1.)
    working_height = 720
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if len(frames) >= 901:
            raise ValueError('clip_too_long')
        source_h, source_w = frame.shape[:2]
        working_height = min(720,source_h)
        if source_h > source_w:
            rw = max(1,round(source_w*360/source_h));ox=(640-rw)//2
            canvas=np.zeros((360,640,3),np.uint8)
            canvas[:,ox:ox+rw]=cv2.resize(frame,(rw,360))
            mapping=(ox/640,0.,rw/640,1.)
        else:canvas=cv2.resize(frame,(640,360))
        frames.append(cv2.cvtColor(canvas,cv2.COLOR_BGR2RGB))
    cap.release()
    if len(frames) < 3:
        raise ValueError('clip_too_short')
    models = Models()
    court = [models.run('TennisCourtNet', {'inFrame': f}) for f in frames[:3]]
    seg = np.median([x['courtSeg'] for x in court], axis=0)
    scores = court[0]['courtSegScores']
    hidden = models.run('TennisVideoNetInitialHidden', {'nil': np.zeros((1, 1, 1))})['h0']
    cell = models.run('TennisVideoNetInitialCell', {'nil': np.zeros((1, 1, 1))})['c0']
    interval = max(2, int(fps / 10))
    gap = max(1, int(fps / 30))
    samples = []
    for i in range(0, len(frames) - gap, interval):
        cnn = models.run('TennisVideoNetCNN', {'inFrame': frames[i], 'nextFrame': frames[i+gap], 'courtSeg': seg})
        rnn = models.run('TennisVideoNetLSTM', {**cnn, 'inHidden': hidden, 'inCell': cell})
        hidden, cell = rnn['outHidden'], rnn['outCell']
        heads = models.run('TennisVideoNet', rnn)
        x, y = heads['imageLocationPred'].reshape(-1)
        samples.append({'time': i/fps, 'kind': int(heads['eventTypePred'][0]),
                        'side': int(heads['courtSidePred'][0]), 'x': float(x), 'y': float(y)})
        progress(0.1 + 0.3*i/len(frames))
    # Native event voting: isolated hit predictions cannot start a hit window.
    runs = []
    current = []
    for sample in samples:
        if current and (sample['time']-current[-1]['time'] > .8001 or
                        sample['kind'] in (1, 2) and current[-1]['kind'] != sample['kind']):
            runs.append(current)
            current = []
        if sample['kind'] in (1, 2):
            current.append(sample)
    if current:
        runs.append(current)
    runs = [r for r in runs if len(r) >= (4 if r[0]['kind'] == 1 else 2)]
    jobs = []
    duration = len(frames)/fps
    for time in np.arange(0, duration, .2):
        proposal = next((s for s in reversed(samples) if s['time'] <= time), samples[0])
        x = min(.625, max(0, proposal['x']-.1875))
        height = min(1.,256/max(256,working_height))
        y = min(1-height, max(0, proposal['y']-height/2))
        jobs.append((max(0, time-.05), min(duration, time+.2), (x, y, .375, height), 'TennisBounceNet'))
    for run in runs:
        if run[0]['kind'] != 1:
            continue
        p = run[0]
        crop = (min(.25, max(0, p['x']-.375)), min(1-256/360, max(0, p['y']-128/360)), .75, 256/360)
        jobs.append((max(0, p['time']-.5), min(duration, run[-1]['time']+.1), crop, 'TennisShotNet'))
    observations = {}
    for index, (start, end, crop, route) in enumerate(jobs):
        x, y, w, h = crop
        context = {}
        if route == 'TennisBounceNet':
            context = models.run('CourtCropNet', {'courtSegScores': scores,
                'cropDimensions': np.array([y,x,y+h,x+w]).reshape(1,1,4,1,1)})
        hidden = np.zeros(650, np.float32)
        cell = hidden.copy()
        previous = None
        for i in range(int(start*fps), min(len(frames), int(end*fps)+2)):
            image = cv2.resize(frames[i][int(y*360):max(int(y*360)+1,int((y+h)*360)),
                                        int(x*640):max(int(x*640)+1,int((x+w)*640))], (480,256))
            if previous is not None:
                cnn = models.run(route+'CNN', {'inFrame': previous, 'nextFrame': image, **context})
                rnn = models.run(route+'LSTM', {**cnn, 'inHidden': hidden, 'inCell': cell})
                hidden, cell = rnn['outHidden'], rnn['outCell']
                head = models.run(route, {**rnn, 'decoderOutput': cnn['decoderOutput']})
                confidence = float(head['heatmapConfidencePred'].reshape(-1)[0])
                py, px = head['heatmapCoordinatePred'].reshape(-1)
                mx,my,mw,mh=mapping
                point = [float((x+px/480*w-mx)/mw), float((y+py/256*h-my)/mh)]
                if confidence >= .975 and all(0 <= p <= 1 for p in point):
                    old = observations.get(i-1)
                    if old is None or confidence > old['confidence']:
                        observations[i-1] = dict(frame=i-1, time=(i-1)/fps, x=point[0], y=point[1], confidence=confidence)
            previous = image
        progress(.4 + .6*(index+1)/len(jobs))
    from pixel_evidence import refine
    observations = refine(frames, observations, mapping)
    # Never bridge long gaps or unrelated detections with an invented line.
    tracks, track = [], []
    for point in sorted(observations.values(), key=lambda p:p['frame']):
        if track and (point['time']-track[-1]['time'] > .12 or
                      np.hypot(point['x']-track[-1]['x'],point['y']-track[-1]['y']) > .18):
            if len(track) >= 4:
                tracks.append(track)
            track = []
        track.append(point)
    if len(track) >= 4:
        tracks.append(track)
    return {'tracks': tracks, 'fps': fps, 'samples': samples, 'adapter': 'acecut-onnx-v1'}
