// Fuses the existing per-product fixed-point accumulation Loop without changing
// its rounding, exponent gate, operation order, or overflow-to-infinity rules.
extern "C" __global__ void fixed_conv(const double* x,const double* xe,
 const double* w,const double* we,double* out,int C,int H,int W,int O,int OH,int OW,
 int KH,int KW,int SY,int SX,int DY,int DX,int GROUPS,int K){
 int index=blockIdx.x*blockDim.x+threadIdx.x;
 if(index>=O*OH*OW)return;
 int ox=index%OW,oy=(index/OW)%OH,oc=index/(OH*OW);
 double acc=0.;
 for(int k=0;k<K;k++){
  int ic=GROUPS>1?oc:k/(KH*KW);
  int rem=k%(KH*KW),iy=oy*SY+(rem/KW)*DY,ix=ox*SX+(rem%KW)*DX;
  int xi=(ic*H+iy)*W+ix,wi=k*O+oc;
  double prod=xe[xi]+we[wi]<-16.?0.:x[xi]*w[wi];
  double scaled=prod*65536.;
  double q=copysign(floor(fabs(scaled)+.5),scaled);
  acc=acc+q;
  if(acc>2147483647.)acc=__longlong_as_double(0x7ff0000000000000ULL);
  else if(acc< -2147483648.)acc=-__longlong_as_double(0x7ff0000000000000ULL);
 }
 out[index]=acc;
}
