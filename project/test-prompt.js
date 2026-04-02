const { default: ollama } = require('ollama');

const transcript = "Hello. How are you?";
const prompt = `You are a voice assistant. Output ONLY valid JSON.
Analyze the "User Input" and output an action JSON.

Format if they want to send an email:
{"action": "send_email", "to": "recipient", "subject": "subject", "body": "email body"}

Format if they are just chatting:
{"action": "reply", "text": "Your helpful polite spoken reply."}

Examples:
User Input: "email my professor"
Output: {"action": "send_email", "to": "professor", "subject": "Hello", "body": "Dear Professor, reaching out to say hello."}
User Input: "hi how are you"
Output: {"action": "reply", "text": "Hello! I am doing great, how can I help?"}

User Input: "${transcript}"
Output: `;

(async () => {
    const res = await ollama.generate({
      model: 'qwen2.5:14b',
      prompt: prompt,
      format: 'json',
      stream: false
    });
    console.log(res.response.trim());
})();
