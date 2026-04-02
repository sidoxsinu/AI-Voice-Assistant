const { default: ollama } = require('ollama');

(async () => {
    const res = await ollama.chat({
      model: 'qwen2.5:14b',
      messages: [
        { role: 'system', content: 'You are an intent parser. Output ONLY JSON.' },
        { role: 'user', content: 'email my professor' },
        { role: 'assistant', content: '{"action":"send_email","to":"professor","subject":"Hello","body":"Dear Professor,"}' },
        { role: 'user', content: 'hi how are you' },
        { role: 'assistant', content: '{"action":"reply","text":"Hello! I am doing great, how can I help you today?"}' },
        { role: 'user', content: 'Hello. How are you?' }
      ],
      format: 'json',
      stream: false
    });
    console.log(res.message.content.trim());
})();
