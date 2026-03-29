require('dotenv').config({ path: `${__dirname}/../.env` });
const express = require('express');
const cors = require('cors');
const path = require('path');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const { google } = require('googleapis');
const nodemailer = require('nodemailer');
const fs = require('fs');
const gmail = require('./gmail');

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

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
const geminiModel = genAI.getGenerativeModel({ 
  model: process.env.GEMINI_MODEL || 'gemini-1.5-flash' 
})

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

If the user explicitly asks to SEND an email, return exactly this JSON structure:
{
  "action": "send_email",
  "to": "<recipient name or email>",
  "subject": "<short inferred subject line>",
  "body": "<full professional email body with greeting and sign-off>"
}

If the user says anything else (general conversation, questions, or unclear requests), return exactly this JSON structure:
{
  "action": "reply",
  "text": "<Your conversational, helpful, and concise spoken reply back to the user. Keep it under 2 sentences.>"
}

Rules for sending emails:
- If user says "my professor" → to: "professor"
- Infer a natural subject from what the user said
- Write the body as a short, polite, professional email
- NEVER include anything outside the JSON object

User voice command: "${transcript}"
`

    const result = await geminiModel.generateContent(prompt)
    const rawText = result.response.text().trim()

    // Strip markdown if Gemini adds it
    const cleaned = rawText
      .replace(/```json\n?/g, '')
      .replace(/```\n?/g, '')
      .trim()

    // Extract JSON object safely
    const jsonMatch = cleaned.match(/\{[\s\S]*\}/)
    if (!jsonMatch) {
      throw new Error('Gemini did not return valid JSON')
    }

    const parsed = JSON.parse(jsonMatch[0])
    console.log('Parsed email intent:', parsed)

    res.json(parsed)

  } catch (error) {
    console.error('Gemini API error:', error.message)
    res.status(500).json({ 
      error: 'Failed to parse voice command',
      details: error.message
    })
  }
})

// Gmail Integration
app.get('/auth/google', (req, res) => {
  const url = gmail.getAuthUrl();
  res.redirect(url);
});

app.get('/auth/google/callback', async (req, res) => {
  try {
    const code = req.query.code;
    await gmail.handleCallback(code);
    res.redirect('/');
  } catch (error) {
    console.error("OAuth Error:", error);
    res.status(500).send("Authentication failed");
  }
});

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

// ElevenLabs TTS
app.post('/api/speak', async (req, res) => {
  try {
    const { text } = req.body;
    const VOICE_ID = '21m00Tcm4TlvDq8ikWAM'; // Rachel
    
    // Node.js 18+ includes Global Fetch API, use direct fetch for ElevenLabs
    const response = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${VOICE_ID}`, {
      method: 'POST',
      headers: {
        'Accept': 'audio/mpeg',
        'xi-api-key': process.env.ELEVENLABS_API_KEY,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        text,
        model_id: "eleven_monolingual_v1",
        voice_settings: {
          stability: 0.5,
          similarity_boost: 0.5
        }
      })
    });
    
    if (!response.ok) {
        throw new Error("TTS Failed");
    }

    const arrayBuffer = await response.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);
    
    res.set({
      'Content-Type': 'audio/mpeg',
      'Content-Length': buffer.length
    });
    res.send(buffer);
  } catch (error) {
    console.error("ElevenLabs Error:", error);
    res.status(500).json({ error: "Failed to generate TTS" });
  }
});

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

    const result = await geminiModel.generateContent(prompt)
    const summary = result.response.text().trim()

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

    const result = await geminiModel.generateContent(prompt)
    const task = result.response.text().trim()

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
