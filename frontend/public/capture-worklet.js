class DuckCapture extends AudioWorkletProcessor {
  process(inputs) {
    if(inputs[0]?.[0]) {
      const copy=inputs[0][0].slice();
      this.port.postMessage(copy,[copy.buffer]);
    }
    return true;
  }
}
registerProcessor('duck-capture',DuckCapture);
