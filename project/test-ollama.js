const { default: ollama } = require('ollama');
(async () => {
  try {
    const res = await ollama.generate({ model: 'qwen2.5:14b', prompt: 'hello' });
    console.log(res);
  } catch (e) {
    console.log(e.message);
  }
})();
