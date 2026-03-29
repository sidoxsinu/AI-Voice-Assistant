const { google } = require('googleapis');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

const oauth2Client = new google.auth.OAuth2(
  process.env.GOOGLE_CLIENT_ID,
  process.env.GOOGLE_CLIENT_SECRET,
  process.env.GOOGLE_REDIRECT_URI
);

// If we already have a refresh token, set it
if (process.env.GOOGLE_REFRESH_TOKEN && process.env.GOOGLE_REFRESH_TOKEN !== 'will_be_filled_after_first_login') {
  oauth2Client.setCredentials({
    refresh_token: process.env.GOOGLE_REFRESH_TOKEN
  });
}

function getAuthUrl() {
  return oauth2Client.generateAuthUrl({
    access_type: 'offline',
    scope: ['https://www.googleapis.com/auth/gmail.send'],
    prompt: 'consent' // Forces it to return a refresh token every time
  });
}

async function handleCallback(code) {
  const { tokens } = await oauth2Client.getToken(code);
  oauth2Client.setCredentials(tokens);
  
  if (tokens.refresh_token) {
    const envPath = path.join(__dirname, '..', '.env');
    let envData = fs.readFileSync(envPath, 'utf8');
    
    // Replace the existing token or add it
    if (envData.includes('GOOGLE_REFRESH_TOKEN=')) {
      envData = envData.replace(/GOOGLE_REFRESH_TOKEN=.*/g, `GOOGLE_REFRESH_TOKEN=${tokens.refresh_token}`);
    } else {
      envData += `\nGOOGLE_REFRESH_TOKEN=${tokens.refresh_token}`;
    }
    
    fs.writeFileSync(envPath, envData);
    process.env.GOOGLE_REFRESH_TOKEN = tokens.refresh_token;
  }
}

async function sendEmail(to, subject, body) {
  const gmail = google.gmail({ version: 'v1', auth: oauth2Client });
  
  const utf8Subject = `=?utf-8?B?${Buffer.from(subject).toString('base64')}?=`;
  const messageParts = [
    `To: ${to}`,
    'Content-Type: text/html; charset=utf-8',
    'MIME-Version: 1.0',
    `Subject: ${utf8Subject}`,
    '',
    body.replace(/\n/g, '<br>')
  ];
  
  const message = messageParts.join('\n');
  const encodedMessage = Buffer.from(message)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');

  const res = await gmail.users.messages.send({
    userId: 'me',
    requestBody: {
      raw: encodedMessage,
    },
  });
  
  return res.data;
}

module.exports = {
  getAuthUrl,
  handleCallback,
  sendEmail
};
