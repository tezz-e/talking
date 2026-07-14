# Talking — AI Texting Autopilot

Talking is a self-hosted AI texting autopilot that learns your texting style, personality, opinions, and relationships to draft replies that sound exactly like you. 

It uses a RAG (Retrieval-Augmented Generation) pipeline backed by a vector database (ChromaDB) containing your chat history, integrated with Gemini for free-form texting generation, and Google Search grounding to handle lyric/meme callback completions.

## Features
- **Semantic Memory**: Search and retrieve context from past conversations using ChromaDB and Gemini embeddings.
- **WhatsApp & Instagram Ingestion**: Import chat exports to extract your unique texting fingerprint (capitalization, emoji frequency, common slang) and build semantic memories.
- **Personality Engine**: Driven by `SOUL.md` (defining who you are, opinions, stories, social style) and `STYLE.md` (defining your texting fingerprint).
- **Callback Overrides**: Automatically learns your corrections to improve future responses.
- **Lyric/Meme Completion**: Uses Google Search grounding to complete song lyrics or memes.

## Getting Started

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/Talking.git
   cd Talking
   ```

2. **Set up the virtual environment**:
   Run the `start_server.bat` script on Windows. It will automatically create a virtual environment, install requirements, and start the server.

3. **Configure environment variables**:
   Create a `.env` file in the root directory:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   # Optional: GROQ_API_KEY=your_groq_api_key_here
   ```

4. **Initialize your profile**:
   Edit `data/SOUL.md` and `data/STYLE.md` to define who you are.

5. **Run the dashboard**:
   Run `start_server.bat` again to start the server at `http://127.0.0.1:8000`.
