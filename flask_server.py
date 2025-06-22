from flask import Flask, request, jsonify
from neo4j import GraphDatabase
import ollama
import os

app = Flask(__name__)

# --- Connection Details ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
OLLAMA_MODEL = "nomic-embed-text"

# --- Neo4j Driver ---
try:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print("Successfully connected to Neo4j.")
except Exception as e:
    print(f"Failed to connect to Neo4j: {e}")
    driver = None

def get_db_session():
    """Gets a session from the Neo4j driver."""
    if driver:
        return driver.session()
    return None

def embed(text: str):
    """Generates an embedding for the given text using Ollama."""
    try:
        return ollama.embeddings(model=OLLAMA_MODEL, prompt=text)["embedding"]
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return []

@app.route('/chat', methods=['POST'])
def chat():
    """
    Handles chat requests from the frontend.
    """
    data = request.get_json()
    user_message = data.get('message')
    print(f"User message: {user_message}")
    print(f"Driver: {driver}")

    if not user_message:
        return jsonify({'error': 'No message provided'}), 400

    if not driver:
        return jsonify({'error': 'Database connection not available'}), 500

    # 1. Generate embedding for the user's message
    message_embedding = embed(user_message)
    if not message_embedding:
        return jsonify({'error': 'Could not generate text embedding.'}), 500

    # 2. Query Neo4j for similar verses and paragraphs
    session = get_db_session()
    if not session:
        return jsonify({'error': 'Could not get database session.'}), 500
        
    try:
        # This query finds the top 3 most similar verses and paragraphs
        # based on the cosine similarity of their embeddings.
        cypher_query = """
        CALL db.index.vector.queryNodes('verse_embedding', 3, $embedding) YIELD node AS verse, score AS v_score
        WITH verse, v_score
        OPTIONAL MATCH (verse)<-[:CONTAINS]-(chapter)<-[:CONTAINS]-(book)
        WITH verse.text AS verse_text, v_score, book.title AS book_title, chapter.number AS chapter_number, verse.number AS verse_number
        WITH collect({text: verse_text, score: v_score, source: book_title + ' ' + chapter_number + ':' + verse_number}) AS verses
        
        CALL db.index.vector.queryNodes('paragraph_embedding', 3, $embedding) YIELD node AS paragraph, score AS p_score
        WITH verses, paragraph, p_score
        OPTIONAL MATCH (paragraph)<-[:CONTAINS]-(talk)
        WITH verses, collect({text: paragraph.text, score: p_score, source: talk.title}) AS paragraphs
        
        RETURN verses, paragraphs
        """
        
        result = session.run(cypher_query, embedding=message_embedding)
        data = result.single()

        if not data:
             return jsonify({'reply': "I couldn't find anything relevant to your question."})

        # 3. Format the results
        verses = data.get('verses', [])
        paragraphs = data.get('paragraphs', [])
        
        # Combine and sort all results by score
        all_results = sorted(verses + paragraphs, key=lambda x: x['score'], reverse=True)
        
        # Format the reply
        if not all_results:
            reply = "I couldn't find any relevant verses or talks for your question."
        else:
            reply_parts = ["Here are some things that might help:"]
            # TODO: Add a way to get more results and have LLM pick the top 3 to return with an explanation
            for item in all_results[:3]: # Get top 3 overall
                reply_parts.append(f"\n- From \"{item['source']}\":\n  \"{item['text']}\"")
            reply = "\n".join(reply_parts)

        return jsonify({'reply': reply})

    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({'error': 'An error occurred while querying the database.'}), 500
    finally:
        if session:
            session.close()

if __name__ == '__main__':
    # Use 0.0.0.0 to make it accessible on local network
    app.run(host='0.0.0.0', port=5000, debug=True)
