"""Compile the fused loop with existing NVRTC; no global CUDA changes."""
import ctypes,subprocess,os
from pathlib import Path
root=Path(__file__).resolve().parent
lib=ctypes.CDLL('/data/envs/torch-cu130/lib/python3.10/site-packages/nvidia/cu13/lib/libnvrtc.so.13')
program=ctypes.c_void_p();source=(root/'fixed_conv.cu').read_bytes()
assert lib.nvrtcCreateProgram(ctypes.byref(program),source,b'fixed_conv.cu',0,None,None)==0
opts=(ctypes.c_char_p*3)(b'--gpu-architecture=compute_86',b'--fmad=false',b'--std=c++11')
r=lib.nvrtcCompileProgram(program,3,opts)
if r:
 size=ctypes.c_size_t();lib.nvrtcGetProgramLogSize(program,ctypes.byref(size));buf=ctypes.create_string_buffer(size.value);lib.nvrtcGetProgramLog(program,buf);raise RuntimeError(buf.value.decode())
size=ctypes.c_size_t();assert lib.nvrtcGetPTXSize(program,ctypes.byref(size))==0
buf=ctypes.create_string_buffer(size.value);assert lib.nvrtcGetPTX(program,buf)==0
(root/'fixed_conv.ptx').write_bytes(buf.value);lib.nvrtcDestroyProgram(ctypes.byref(program))
subprocess.run(['g++','-std=c++17','-O2','-shared','-fPIC','-I'+os.environ.get('ORT_HEADERS','/data/swi-algo/Swi-AI-Editing/repo/temp/jianying_macos_research_20260917/ort_sdk_1_23_2'),str(root/'fixed_conv.cc'),'-ldl','-o',str(root/'fixed_conv.so')],check=True)
print('Built fused convolution operator')
