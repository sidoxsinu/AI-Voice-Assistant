const { default: ollama } = require('ollama');

const transcript = "Hi. How are you?";
const prompt = `Analyze the user's voice command: "${transcript}"

If the user explicitly asks to draft or send an email, output this JSON structure:
{"action": "send_email", "to": "recipient", "subject": "subject", "body": "email body"}

If it is general conversation or a question, output this JSON structure:
{"action": "reply", "text": "Your helpful polite response."}

Output only the JSON object.`;

(async () => {
    const res = await ollama.generate({
      model: 'qwen2.5:14b',
      prompt: prompt,
      format: 'json',
      stream: false
    });
    console.log(res.response.trim());
})();
