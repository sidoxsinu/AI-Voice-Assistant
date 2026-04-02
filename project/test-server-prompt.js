const { default: ollama } = require('ollama');

const transcript = "Hi. How are you?";
const prompt = `Analyze the user's voice command. Does the user explicitly ask to draft or send an email?
If YES, output this JSON structure:
{"action": "send_email", "to": "recipient", "subject": "subject", "body": "polite email body"}

If NO (general conversation or questions), output this JSON structure:
{"action": "reply", "text": "Your helpful polite spoken reply."}

Examples:
User: "shoot an email to my professor I'll be late"
Output: {"action": "send_email", "to": "professor", "subject": "Late for Meeting", "body": "Dear Professor, I will be late for our meeting. Apologies."}

User: "hello how are you"
Output: {"action": "reply", "text": "Hello! I am doing great. How can I assist you today?"}

User: "${transcript}"
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
