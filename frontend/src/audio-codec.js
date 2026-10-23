// Streaming linear resampling and PCM16 framing, independent of browser audio APIs.
export class PCMFramer {
  constructor(inputRate, outputRate=16000, frameSamples=960) {
    if(!Number.isFinite(inputRate)||inputRate<8000||inputRate>192000||outputRate!==16000||frameSamples!==960) throw new Error('Unsupported audio format');
    this.ratio=inputRate/outputRate;this.pending=[];this.position=0;this.output=[];this.frameSamples=frameSamples;
  }
  push(samples) {
    this.pending.push(...samples);
    while(this.position+1<this.pending.length){
      const index=Math.floor(this.position), fraction=this.position-index;
      const left=Number.isFinite(this.pending[index])?this.pending[index]:0;
      const right=Number.isFinite(this.pending[index+1])?this.pending[index+1]:0;
      const sample=left*(1-fraction)+right*fraction;
      const bounded=Number.isFinite(sample)?Math.max(-1,Math.min(1,sample)):0;
      this.output.push(Math.round(bounded*(bounded<0?32768:32767)));
      this.position+=this.ratio;
    }
    const consumed=Math.min(Math.floor(this.position),Math.max(0,this.pending.length-1));
    this.pending=this.pending.slice(consumed);this.position-=consumed;
    const frames=[];
    while(this.output.length>=this.frameSamples)frames.push(this.pack(this.output.splice(0,this.frameSamples)));
    return frames;
  }
  pack(samples){
    const buffer=new ArrayBuffer(this.frameSamples*2),view=new DataView(buffer);
    samples.forEach((value,index)=>view.setInt16(index*2,value,true));return buffer;
  }
  flush(){
    // Finish the last interpolation endpoint and zero-pad only the final partial frame.
    const frames=this.pending.length?this.push([this.pending.at(-1)]):[];
    if(this.output.length)frames.push(this.pack(this.output.splice(0)));
    this.pending=[];this.position=0;return frames;
  }
}

export function decodePCM(base64){
  const binary=atob(base64);
  if(binary.length%2)throw new Error('Invalid PCM16 payload');
  const bytes=Uint8Array.from(binary,ch=>ch.charCodeAt(0)),view=new DataView(bytes.buffer);
  const values=new Float32Array(bytes.length/2);
  for(let i=0;i<values.length;i++)values[i]=view.getInt16(i*2,true)/32768;
  return values;
}
