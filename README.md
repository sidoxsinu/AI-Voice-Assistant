# AI Voice-First Task Assistant

A voice-first task assistant that leverages AI to help with email drafting, task management, and Gmail integration. The application uses a local Ollama model (Qwen 2.5 14B) to understand natural language commands and interacts with Gmail for sending emails.

## Features

- **Voice Input**: Process voice commands through Deepgram API
- **AI-Powered Processing**: Uses Ollama (Qwen 2.5 14B) for intelligent command parsing locally
- **Gmail Integration**: Seamlessly draft and send emails
- **Task Management**: Manage to-do items
- **Email Composition**: Natural language email drafting
- **CORS Enabled**: Full frontend-backend communication support

## Prerequisites

Before running this project, ensure you have the following installed:

- **Node.js** (v25.8.2 installed) - [Download](https://nodejs.org/)
- **npm** (v11.11.1 installed, comes with Node.js)
- **Docker & Docker Compose** (optional, for containerized setup) - [Download](https://www.docker.com/)

> ✅ Node.js and npm have been successfully installed on this system.

## Environment Setup
rename the .env.example file to .env and fill in the following values as instructed in the .env.example file:

```
DEEPGRAM_API_KEY=your_deepgram_api_key_here
OLLAMA_MODEL=your_model_name_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
GMAIL_USER=your_email@gmail.com
GMAIL_PASS=xxxx xxxx xxxx xxxx
```

### How to Get API Keys

Check the .env.example file for instructions

## Installation

### 1. Clone/Navigate to Project

```bash
cd /Users/sinanm/Documents/Projects/AI-Voice-Assistant
```

### 2. Install Dependencies (two options)

- From root (recommended, now supported by root package.json):

```bash
npm install
```

- Or from `project` folder:

```bash
cd project
npm install
```

## Running the Application

### Option 1: Local Development (Without Docker)

1. **Install dependencies** (if not already done):
   - from root:
     ```bash
     npm install
     ```
   - or from project:
     ```bash
     cd project
     npm install
     ```

2. **Start the server**:
   - from root:
     ```bash
     npm start
     ```
   - or from project:
     ```bash
     cd project
     npm start
     ```

3. **Access the application**:
   Open your browser and navigate to:
   ```
   http://localhost:3000
   ```

The server will start on port 3000 and serve the frontend files.

### Option 2: Docker (Recommended for Production)

1. **Ensure Docker is running** on your system

2. **Build and start the container**:
   ```bash
   docker-compose up --build
   ```

3. **Access the application**:
   Open your browser and navigate to:
   ```
   http://localhost:3000
   ```

4. **Stop the application**:
   ```bash
   docker-compose down
   ```

#### Docker Compose Details

The `docker-compose.yml` is configured with:
- Node.js 20 Alpine image for minimal footprint
- Port mapping: `3000:3000`
- Volume mounting for live code reloading during development
- Node modules persistence to prevent reinstallation

## Verification Steps - ✅ Successfully Tested

The application has been verified to run successfully with the following steps:

### Prerequisites Met ✅
- Node.js v25.8.2 installed
- npm v11.11.1 installed
- All dependencies installed via `npm install`

### Successful Startup ✅
1. Navigate to the `project` directory
2. Create a `.env` file with required environment variables
3. Run `npm start` from the project directory
4. Server starts and listens on port 3000
5. Frontend is accessible at `http://localhost:3000`

### What to Expect
- The application serves the frontend HTML on port 3000
- The backend Express server handles API requests
- Voice commands can be sent to `/api/parse-command` endpoint
- Deepgram API key and Ollama model config are loaded from `.env` file

## Project Structure

```
project/
├── index.html              # Frontend HTML file
├── package.json            # Node.js dependencies and scripts
├── Dockerfile              # Docker configuration
├── docker-compose.yml      # Docker Compose orchestration
├── backend/
│   ├── server.js          # Main Express server
│   ├── gmail.js           # Gmail integration utilities
│   └── todo.txt           # To-do storage file
└── .env                    # Environment variables (create this file)
```

## Usage

### Available API Endpoints

- **POST /api/parse-command** - Parse voice transcript into structured commands
- **GET /api/env** - Get frontend configuration (Deepgram API key)
- **GET /api/** - Serve static frontend files

### Voice Command Examples

The assistant understands natural language commands such as:
- "Send an email to John about the project"
- "Draft a message thanking Sarah"
- "Add buy groceries to my to-do list"

## Development

### Running in Development Mode

For active development with auto-reload capabilities, use Docker Compose:

```bash
docker-compose up
```

This sets up volume mounts allowing you to edit files and see changes reflected immediately.

### Debugging

Enable Node.js debugging by modifying the Dockerfile or docker-compose.yml:

```yaml
CMD ["node", "--inspect=0.0.0.0:9229", "backend/server.js"]
```

## Dependencies

- **express** - Web server framework
- **ollama** - Local AI model integration via Ollama
- **googleapis** - Google APIs client library
- **nodemailer** - Email sending functionality
- **cors** - Cross-Origin Resource Sharing support
- **dotenv** - Environment variable management

## Troubleshooting

### Port 3000 Already in Use

If port 3000 is already in use:
- **Local**: Modify the port in `docker-compose.yml` or use environment variable
- **Docker**: Change the port mapping in docker-compose.yml from `"3000:3000"` to `"3001:3000"`

### Module Not Found Errors

```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install
```

### Environment Variables Not Loading

- Verify `.env` file is in the `project` directory
- Ensure variable names match exactly (case-sensitive)
- Restart the server after changes

## Docker Troubleshooting

### Rebuild Docker Image

```bash
docker-compose build --no-cache
```

### View Logs

```bash
docker-compose logs -f
```

### Remove Containers and Volumes

```bash
docker-compose down -v
```

## Performance Optimization

- The Dockerfile uses `node:20-alpine` for minimal image size (~150MB)
- Volume mounts in Docker Compose cache dependencies for faster rebuilds
- Static files are served directly through Express for efficiency

## Production Deployment

For production deployment:

1. Set `NODE_ENV=production` environment variable
2. Use environment-specific `.env` files
3. Configure appropriate CORS origins
4. Use a process manager like PM2 for Node.js
5. Implement proper error logging and monitoring

## License

Specify your project license here.

## Support

For issues or questions, please refer to the main project documentation or create an issue in the repository.
