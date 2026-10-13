// Some managed Windows installations still use Edge 96. Transpilation does
// not polyfill built-ins used by the Markdown renderer.
if (!Object.hasOwn) {
  Object.defineProperty(Object, 'hasOwn', {
    value: (object: object, key: PropertyKey) => Object.prototype.hasOwnProperty.call(object, key),
    writable: true, configurable: true,
  });
}
