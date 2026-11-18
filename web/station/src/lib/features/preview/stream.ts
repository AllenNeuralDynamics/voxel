import type { DecodedLiveFrame, LiveWorkerCommand, LiveWorkerEvent } from './protocol';

type FrameHandler = (frame: DecodedLiveFrame) => void;

/** Browser-side lifecycle for the dedicated preview socket and decoder worker. */
export class LiveStream {
  readonly #worker: Worker;
  readonly #frameHandler: FrameHandler;
  readonly #errorHandler: (message: string | null) => void;
  readonly #visibilityHandler: () => void;

  constructor(
    websocketUrl: string,
    protocolVersion: number,
    frameHandler: FrameHandler,
    errorHandler: (message: string | null) => void
  ) {
    this.#frameHandler = frameHandler;
    this.#errorHandler = errorHandler;
    this.#worker = new Worker(new URL('./stream.worker.ts', import.meta.url), { type: 'module' });
    this.#worker.onmessage = (event: MessageEvent<LiveWorkerEvent>) => this.#handleEvent(event.data);
    this.#worker.onerror = (event) => this.#errorHandler(event.message || 'Preview decoder worker failed.');
    this.#visibilityHandler = () => this.#post({ type: 'visibility', visible: !document.hidden });
    document.addEventListener('visibilitychange', this.#visibilityHandler);
    this.#post({
      type: 'configure',
      websocketUrl,
      protocolVersion,
      visible: !document.hidden
    });
  }

  flush(): void {
    this.#post({ type: 'flush' });
  }

  dispose(): void {
    document.removeEventListener('visibilitychange', this.#visibilityHandler);
    this.#post({ type: 'close' });
    this.#worker.terminate();
  }

  #post(command: LiveWorkerCommand): void {
    this.#worker.postMessage(command);
  }

  #handleEvent(event: LiveWorkerEvent): void {
    switch (event.type) {
      case 'frame':
        this.#errorHandler(null);
        this.#frameHandler(event.frame);
        break;
      case 'error':
        this.#errorHandler(event.message);
        break;
      case 'state':
        break;
    }
  }
}
