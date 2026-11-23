"""Fuse only the recognized, verified fixed-convolution Loop template."""
import json,sys,hashlib
from pathlib import Path
import onnx
from onnx import helper as h,numpy_helper as nh

def fuse(source,destination):
    model=onnx.load(source);const={x.name:nh.to_array(x) for x in model.graph.initializer};nodes=[];count=0
    scalar=lambda name:int(const[name].item())
    for node in model.graph.node:
        if node.op_type!='Loop':nodes.append(node);continue
        body=next(a.g for a in node.attribute if a.name=='body');b=list(body.node)
        expected=['Div','Mod','Div','Mul','Mod','Mul','Unsqueeze','Unsqueeze','Unsqueeze','Concat','Add','Slice','Slice','Gather','Reshape','Gather','Reshape','Add','Less','Mul','Where','Mul','Sign','Abs','Add','Floor','Mul','Add']
        if [x.op_type for x in b[:28]]!=expected: nodes.append(node);continue
        # Reject a different quantizer rather than silently relaxing the model.
        assert float(const[b[18].input[1]])==-16
        assert float(const[b[21].input[1]])==65536
        assert float(const[b[24].input[1]])==.5
        shape=[d.dim_value for d in body.output[1].type.tensor_type.shape.dim]
        assert len(shape)==4 and shape[0]==1
        _,O,OH,OW=shape;area=scalar(b[0].input[1]);KW=scalar(b[2].input[1]);KH=area//KW
        assert KH*KW==area
        steps=const[b[11].input[4]].tolist();extent=const[b[10].input[1]].tolist()
        assert steps[:2]==[1,1] and extent[0]==1 and extent[1] in (1,O)
        attrs=dict(O=O,OH=OH,OW=OW,KH=KH,KW=KW,SY=int(steps[2]),SX=int(steps[3]),
                   DY=scalar(b[3].input[1]),DX=scalar(b[5].input[1]),GROUPS=int(extent[1]),K=scalar(node.input[0]),
                   ptx=str(Path(__file__).with_name('fixed_conv.ptx')))
        nodes.append(h.make_node('FixedConvLoop',[b[11].input[0],b[12].input[0],b[13].input[0],b[15].input[0]],
                                list(node.output),name=node.name+'_fused',domain='swie',**attrs));count+=1
    assert count>0
    del model.graph.node[:];model.graph.node.extend(nodes)
    model.opset_import.append(h.make_opsetid('swie',1))
    onnx.checker.check_model(model);onnx.save(model,destination)
    return dict(source=str(source),sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),fused_loops=count,
                destination=str(destination),output_sha256=hashlib.sha256(Path(destination).read_bytes()).hexdigest())
if __name__=='__main__':print(json.dumps(fuse(Path(sys.argv[1]),Path(sys.argv[2])),indent=2))
