/**
 * Lightweight typed key-value wrapper around IndexedDB.
 *
 * Each instance manages a single object store within a named database.
 * Values can be any structured-cloneable type (objects, Blobs, ArrayBuffers, etc.).
 */
export class IDBKeyVal<T> {
	readonly #dbName: string;
	readonly #storeName: string;
	#db: IDBDatabase | null = null;

	constructor(dbName: string, storeName = 'store') {
		this.#dbName = dbName;
		this.#storeName = storeName;
	}

	#open(): Promise<IDBDatabase> {
		if (this.#db) return Promise.resolve(this.#db);
		return new Promise((resolve, reject) => {
			const req = indexedDB.open(this.#dbName, 1);
			req.onupgradeneeded = () => {
				req.result.createObjectStore(this.#storeName);
			};
			req.onsuccess = () => {
				this.#db = req.result;
				resolve(req.result);
			};
			req.onerror = () => reject(req.error);
		});
	}

	#tx(mode: IDBTransactionMode): Promise<IDBObjectStore> {
		return this.#open().then((db) => db.transaction(this.#storeName, mode).objectStore(this.#storeName));
	}

	static #wrap<R>(req: IDBRequest<R>): Promise<R> {
		return new Promise((resolve, reject) => {
			req.onsuccess = () => resolve(req.result);
			req.onerror = () => reject(req.error);
		});
	}

	async get(key: string): Promise<T | undefined> {
		const store = await this.#tx('readonly');
		return IDBKeyVal.#wrap<T | undefined>(store.get(key));
	}

	async put(key: string, value: T): Promise<void> {
		const store = await this.#tx('readwrite');
		await IDBKeyVal.#wrap(store.put(value, key));
	}

	async delete(key: string): Promise<void> {
		const store = await this.#tx('readwrite');
		await IDBKeyVal.#wrap(store.delete(key));
	}

	async entries(): Promise<[string, T][]> {
		const store = await this.#tx('readonly');
		const [keys, values] = await Promise.all([
			IDBKeyVal.#wrap(store.getAllKeys()),
			IDBKeyVal.#wrap<T[]>(store.getAll())
		]);
		return keys.map((k, i) => [String(k), values[i]]);
	}

	async clear(): Promise<void> {
		const store = await this.#tx('readwrite');
		await IDBKeyVal.#wrap(store.clear());
	}
}
