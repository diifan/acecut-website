#define ORT_API_MANUAL_INIT
#include "onnxruntime_cxx_api.h"
#include <dlfcn.h>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <mutex>
using Module=void*;using Function=void*;using Stream=void*;
struct Driver {
 void* lib=dlopen("libcuda.so.1",RTLD_NOW);
 int (*load)(Module*,const void*)=(decltype(load))dlsym(lib,"cuModuleLoadData");
 int (*function)(Function*,Module,const char*)=(decltype(function))dlsym(lib,"cuModuleGetFunction");
 int (*launch)(Function,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,Stream,void**,void**)=(decltype(launch))dlsym(lib,"cuLaunchKernel");
};
struct Kernel {
 const OrtApi& api;int O,OH,OW,KH,KW,SY,SX,DY,DX,GROUPS,K;std::string ptx;Module module=nullptr;Function function=nullptr;
 Kernel(const OrtApi& a,const OrtKernelInfo* info):api(a){
  Ort::ConstKernelInfo i(info);
  O=i.GetAttribute<int64_t>("O");OH=i.GetAttribute<int64_t>("OH");OW=i.GetAttribute<int64_t>("OW");
  KH=i.GetAttribute<int64_t>("KH");KW=i.GetAttribute<int64_t>("KW");SY=i.GetAttribute<int64_t>("SY");SX=i.GetAttribute<int64_t>("SX");
  DY=i.GetAttribute<int64_t>("DY");DX=i.GetAttribute<int64_t>("DX");GROUPS=i.GetAttribute<int64_t>("GROUPS");K=i.GetAttribute<int64_t>("K");
  std::ifstream in(i.GetAttribute<std::string>("ptx"));std::stringstream s;s<<in.rdbuf();ptx=s.str();
  if(ptx.empty())throw std::runtime_error("Missing fixed-convolution PTX");
 }
 void Compute(OrtKernelContext* raw){
  Ort::KernelContext ctx(raw);static Driver driver;
  if(!driver.lib||!driver.load||!driver.function||!driver.launch)throw std::runtime_error("CUDA driver unavailable");
  if(!module){if(driver.load(&module,ptx.c_str())||driver.function(&function,module,"fixed_conv"))throw std::runtime_error("CUDA module failed");}
  auto a=ctx.GetInput(0);auto shape=a.GetTensorTypeAndShapeInfo().GetShape();int C=shape[1],H=shape[2],W=shape[3];
  const double* x=a.GetTensorData<double>();const double* xe=ctx.GetInput(1).GetTensorData<double>();
  const double* w=ctx.GetInput(2).GetTensorData<double>();const double* we=ctx.GetInput(3).GetTensorData<double>();
  auto output=ctx.GetOutput(0,std::vector<int64_t>{1,O,OH,OW});double* out=output.GetTensorMutableData<double>();
  void* stream=nullptr;Ort::ThrowOnError(api.KernelContext_GetGPUComputeStream(raw,&stream));
  void* args[]={&x,&xe,&w,&we,&out,&C,&H,&W,&O,&OH,&OW,&KH,&KW,&SY,&SX,&DY,&DX,&GROUPS,&K};
  if(driver.launch(function,(O*OH*OW+127)/128,1,1,128,1,1,0,stream,args,nullptr))throw std::runtime_error("CUDA convolution launch failed");
 }
};
struct Op:Ort::CustomOpBase<Op,Kernel>{
 void* CreateKernel(const OrtApi& api,const OrtKernelInfo* info)const{return new Kernel(api,info);}
 const char* GetName()const{return "FixedConvLoop";}
 const char* GetExecutionProviderType()const{return "CUDAExecutionProvider";}
 size_t GetInputTypeCount()const{return 4;}size_t GetOutputTypeCount()const{return 1;}
 ONNXTensorElementDataType GetInputType(size_t)const{return ONNX_TENSOR_ELEMENT_DATA_TYPE_DOUBLE;}
 ONNXTensorElementDataType GetOutputType(size_t)const{return ONNX_TENSOR_ELEMENT_DATA_TYPE_DOUBLE;}
};
extern "C" OrtStatus* ORT_API_CALL RegisterCustomOps(OrtSessionOptions* options,const OrtApiBase* base){
 auto api=base->GetApi(ORT_API_VERSION);Ort::InitApi(api);static Op op;static OrtCustomOpDomain* domain=nullptr;static std::once_flag once;
 try{std::call_once(once,[&]{Ort::ThrowOnError(api->CreateCustomOpDomain("swie",&domain));Ort::ThrowOnError(api->CustomOpDomain_Add(domain,&op));});return api->AddCustomOpDomain(options,domain);}
 catch(const std::exception& e){return api->CreateStatus(ORT_FAIL,e.what());}
}
