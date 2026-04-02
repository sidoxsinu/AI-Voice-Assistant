require('dotenv').config({ path: `${__dirname}/../.env` });
const express = require('express');
const cors = require('cors');
const path = require('path');
const { Ollama } = require('ollama')
const ollama = new Ollama({ host: 'http://localhost:11434' })
const { google } = require('googleapis');
const nodemailer = require('nodemailer');
const fs = require('fs');

const TODO_FILE = path.join(__dirname, 'todo.txt');

const app = express();
app.use(cors());
app.use(express.json());

// Serve the frontend statically
app.use(express.static(path.join(__dirname, '..')));

// Env keys for frontend
app.get('/api/env', (req, res) => {
  res.json({ deepgramKey: process.env.DEEPGRAM_API_KEY });
});

const ollamaModel = process.env.OLLAMA_MODEL || 'qwen2.5:14b';

app.post('/api/parse-command', async (req, res) => {
  try {
    const { transcript } = req.body

    if (!transcript) {
      return res.status(400).json({ error: 'No transcript provided' })
    }

    console.log('Received transcript:', transcript)

    const prompt = `
You are a conversational voice assistant that specializes in drafting emails.
The user will speak a natural language command or statement.
Your ONLY job is to return a raw JSON object — 
no markdown, no backticks, no explanation, nothing else.

Analyze the user's voice command. Does the user explicitly ask to draft or send an email?
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
Output: `

    const result = await ollama.generate({
      model: ollamaModel,
      prompt: prompt,
      format: 'json',
      stream: false
    })
    const rawText = result.response.trim()

    // Strip markdown if the model adds it
    const cleaned = rawText
      .replace(/```json\n?/g, '')
      .replace(/```\n?/g, '')
      .trim()

    // Extract JSON object safely
    const jsonMatch = cleaned.match(/\{[\s\S]*\}/)
    if (!jsonMatch) {
      console.error('Ollama did not return valid JSON. Raw text:', cleaned)
      return res.json({ action: 'reply', text: cleaned || "I didn't quite catch that. Could you repeat?" })
    }

    const parsed = JSON.parse(jsonMatch[0])
    console.log('Parsed email intent:', parsed)

    res.json(parsed)

  } catch (error) {
    console.error('Ollama API error:', error.message)
    res.status(500).json({
      error: 'Failed to parse voice command',
      details: error.message
    })
  }
})

// Gmail Integration via App Passwords
app.post('/api/send-email', async (req, res) => {
  try {
    const { to, subject, body } = req.body

    const transporter = nodemailer.createTransport({
      service: 'gmail',
      auth: {
        user: process.env.GMAIL_USER,
        pass: process.env.GMAIL_PASS
      }
    });

    const info = await transporter.sendMail({
      from: `"Voice Assistant" <${process.env.GMAIL_USER}>`,
      to: to,
      subject: subject,
      text: body,
    });

    console.log("Message sent to %s: %s", to, info.messageId);
    res.json({ success: true })

  } catch (error) {
    console.error('Gmail send error:', error)
    res.status(500).json({ success: false, error: error.message })
  }
})


app.post('/api/summarize', async (req, res) => {
  try {
    const { text } = req.body

    if (!text) {
      return res.status(400).json({ error: 'No text provided' })
    }

    const prompt = `Summarize the following text in 3 
sentences or less. Be concise and clear. 
Return only the summary, nothing else:

"${text}"`

    const result = await ollama.generate({
      model: ollamaModel,
      prompt: prompt,
      stream: false
    })
    const summary = result.response.trim()

    res.json({ summary })

  } catch (error) {
    console.error('Summary error:', error)
    res.status(500).json({ error: 'Failed to summarize' })
  }
})

app.post('/api/add-todo', async (req, res) => {
  try {
    const { transcript } = req.body

    const prompt = `Extract only the task item from 
this voice command. Return just the task text, 
nothing else, no punctuation at the end:

"${transcript}"`

    const result = await ollama.generate({
      model: ollamaModel,
      prompt: prompt,
      stream: false
    })
    const task = result.response.trim()

    const timestamp = new Date().toLocaleString()
    const line = `[ ] ${task}  — added ${timestamp}\n`

    fs.appendFileSync(TODO_FILE, line, 'utf8')

    const allTasks = fs.readFileSync(TODO_FILE, 'utf8')
      .split('\n')
      .filter(l => l.trim() !== '')

    res.json({ success: true, task, allTasks })

  } catch (error) {
    console.error('Todo error:', error)
    res.status(500).json({ error: 'Failed to add task' })
  }
})

app.get('/api/todos', (req, res) => {
  try {
    if (!fs.existsSync(TODO_FILE)) return res.json({ tasks: [] })
    const tasks = fs.readFileSync(TODO_FILE, 'utf8')
      .split('\n').filter(l => l.trim() !== '')
    res.json({ tasks })
  } catch (e) {
    res.status(500).json({ error: 'Could not read list' })
  }
})

app.delete('/api/todos', (req, res) => {
  try {
    fs.writeFileSync(TODO_FILE, '', 'utf8')
    res.json({ success: true, tasks: [] })
  } catch (e) {
    res.status(500).json({ error: 'Could not clear list' })
  }
})

app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, '..', 'index.html'));
});

// Handle 404 falling back to index so static resources work
app.use((req, res) => {
  res.sendFile(path.join(__dirname, '..', 'index.html'));
});


const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});
