import {defineConfig} from 'vite';

// Keep media queries compatible with the Windows Edge used for acceptance.
export default defineConfig({build:{target:'es2020',cssTarget:'chrome90'}});
