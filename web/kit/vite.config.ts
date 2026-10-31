import { defineConfig } from 'vite-plus';

export default defineConfig({
  lint: {
    // The kit's tsconfig maps `$lib` to the kit for the shadcn tool, but in an app build `$lib` is the app's folder.
    rules: {
      'no-restricted-imports': [
        'error',
        { patterns: [{ group: ['$lib', '$lib/**'], message: 'Import kit files by relative path.' }] }
      ]
    }
  }
});
