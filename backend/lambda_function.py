import json
import logging
import boto3
import os
from urllib.parse import unquote_plus
from datetime import datetime
import base64
import uuid
import io
import re
from typing import List, Dict
from botocore.config import Config

# === IMPORT PDF LIBRARIES (must be before pg8000 to avoid conflicts) ===
import pdfplumber
import tiktoken

# === IMPORT DATABASE LIBRARY ===
import pg8000

# === SETUP LOGGING ===
logger = logging.getLogger()
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

# === AWS CLIENTS (WITH TIMEOUT CONFIGURATION) ===
s3_config = Config(
    connect_timeout=5,
    read_timeout=10,
    retries={'max_attempts': 1}
)
s3_client = boto3.client('s3', config=s3_config, region_name='us-east-1')

# Bedrock clients
bedrock_runtime_client = boto3.client('bedrock-runtime', region_name='us-east-1')
bedrock_client = boto3.client('bedrock', region_name='us-east-1')

S3_BUCKET = os.environ.get('S3_BUCKET', 'my-demo-bucket-911')

# === DATABASE CONFIGURATION ===
DB_HOST = os.environ.get('DB_HOST', 'doc-db.c0d20mkcufuk.us-east-1.rds.amazonaws.com')
DB_PORT = int(os.environ.get('DB_PORT', '5432'))
DB_NAME = os.environ.get('DB_NAME', 'documents_db')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'YourStrongPassword123!')

# ============================================
# HELPER: Create HTTP Response
# ============================================
def create_response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
        },
        'body': json.dumps(body, default=str)
    }

# ============================================
# DATABASE CONNECTION
# ============================================
def get_db_connection():
    try:
        conn = pg8000.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            timeout=10
        )
        logger.info(f"✅ Connected to database: {DB_NAME}")
        return conn
    except Exception as e:
        logger.error(f"❌ Database connection failed: {str(e)}")
        return None

# ============================================
# DATABASE OPERATIONS
# ============================================
def save_document_metadata(filename, s3_key, metadata=None):
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor()
        metadata_json = json.dumps(metadata or {})
        
        cursor.execute("""
            INSERT INTO documents (id, filename, s3_key, metadata, status)
            VALUES (gen_random_uuid(), %s, %s, %s::jsonb, 'uploaded')
            RETURNING id, filename, upload_date
        """, (filename, s3_key, metadata_json))
        
        result = cursor.fetchone()
        conn.commit()
        
        logger.info(f"✅ Saved document to DB: {filename}")
        return {
            'id': str(result[0]),
            'filename': result[1],
            'upload_date': result[2].isoformat() if result[2] else None
        }
        
    except Exception as e:
        logger.error(f"❌ Database error: {str(e)}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()

def get_all_documents_db(limit=50, offset=0):
    conn = get_db_connection()
    if not conn:
        return {'documents': [], 'total': 0}
    
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                id::text as id,
                filename,
                s3_key,
                upload_date,
                total_chunks,
                status,
                metadata
            FROM documents
            ORDER BY upload_date DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))
        
        results = cursor.fetchall()
        
        cursor.execute("SELECT COUNT(*) FROM documents")
        total = cursor.fetchone()[0]
        
        documents = []
        for row in results:
            doc = {
                'id': row[0],
                'filename': row[1],
                's3_key': row[2],
                'upload_date': row[3].isoformat() if row[3] else None,
                'total_chunks': row[4],
                'status': row[5],
                'metadata': row[6]
            }
            documents.append(doc)
        
        return {
            'documents': documents,
            'total': total,
            'limit': limit,
            'offset': offset
        }
        
    except Exception as e:
        logger.error(f"❌ Database error: {str(e)}")
        return {'documents': [], 'total': 0}
    finally:
        cursor.close()
        conn.close()

def get_document_by_id_db(document_id):
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                id::text as id,
                filename,
                s3_key,
                upload_date,
                total_chunks,
                status,
                metadata
            FROM documents
            WHERE id = %s::uuid
        """, (document_id,))
        
        result = cursor.fetchone()
        
        if result:
            return {
                'id': result[0],
                'filename': result[1],
                's3_key': result[2],
                'upload_date': result[3].isoformat() if result[3] else None,
                'total_chunks': result[4],
                'status': result[5],
                'metadata': result[6]
            }
        return None
        
    except Exception as e:
        logger.error(f"❌ Database error: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_chunks_by_document_db(document_id):
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                id::text as id,
                chunk_index,
                text,
                token_count,
                created_at
            FROM chunks
            WHERE document_id = %s::uuid
            ORDER BY chunk_index
        """, (document_id,))
        
        results = cursor.fetchall()
        
        chunks = []
        for row in results:
            chunk = {
                'id': row[0],
                'chunk_index': row[1],
                'text': row[2],
                'token_count': row[3],
                'created_at': row[4].isoformat() if row[4] else None
            }
            chunks.append(chunk)
        
        return chunks
        
    except Exception as e:
        logger.error(f"❌ Database error: {str(e)}")
        return []
    finally:
        cursor.close()
        conn.close()

# ============================================
# PDF PROCESSING FUNCTIONS
# ============================================

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extract text from PDF using pdfplumber
    """
    try:
        text = ""
        
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages_to_process = min(len(pdf.pages), 10)
            
            for i in range(pages_to_process):
                page = pdf.pages[i]
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"
        
        logger.info(f"✅ Extracted {len(text)} characters from PDF")
        return text
        
    except Exception as e:
        logger.error(f"❌ PDF extraction error: {str(e)}")
        return ""

def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """
    Count tokens using tiktoken
    """
    try:
        encoding = tiktoken.get_encoding(model)
        tokens = encoding.encode(text)
        return len(tokens)
    except Exception as e:
        logger.error(f"❌ Token counting error: {str(e)}")
        return len(text) // 4

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> List[Dict]:
    """
    Split text into overlapping chunks of approximately chunk_size tokens
    """
    logger.info(f"📝 Chunking text ({len(text)} characters)")
    
    paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    chunks = []
    current_chunk = ""
    current_tokens = 0
    
    for para in paragraphs:
        para_tokens = count_tokens(para)
        
        if para_tokens > chunk_size:
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sentence in sentences:
                sentence_tokens = count_tokens(sentence)
                if current_tokens + sentence_tokens > chunk_size and current_chunk:
                    chunks.append({
                        'text': current_chunk.strip(),
                        'token_count': current_tokens
                    })
                    overlap_text = current_chunk[-100:] if len(current_chunk) > 100 else current_chunk
                    current_chunk = overlap_text + " " + sentence
                    current_tokens = count_tokens(current_chunk)
                else:
                    if current_chunk:
                        current_chunk += " " + sentence
                    else:
                        current_chunk = sentence
                    current_tokens += sentence_tokens
        else:
            if current_tokens + para_tokens > chunk_size and current_chunk:
                chunks.append({
                    'text': current_chunk.strip(),
                    'token_count': current_tokens
                })
                overlap_text = current_chunk[-100:] if len(current_chunk) > 100 else current_chunk
                current_chunk = overlap_text + " " + para
                current_tokens = count_tokens(current_chunk)
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
                current_tokens += para_tokens
    
    if current_chunk:
        chunks.append({
            'text': current_chunk.strip(),
            'token_count': current_tokens
        })
    
    for i, chunk in enumerate(chunks):
        chunk['chunk_index'] = i
    
    logger.info(f"✅ Created {len(chunks)} chunks")
    return chunks

def save_chunks_to_db(document_id: str, chunks: List[Dict]) -> bool:
    """
    Save chunks to database
    """
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        for chunk in chunks:
            cursor.execute("""
                INSERT INTO chunks (document_id, chunk_index, text, token_count)
                VALUES (%s::uuid, %s, %s, %s)
            """, (document_id, chunk['chunk_index'], chunk['text'], chunk['token_count']))
        
        cursor.execute("""
            UPDATE documents 
            SET total_chunks = %s, status = 'processed'
            WHERE id = %s::uuid
        """, (len(chunks), document_id))
        
        conn.commit()
        logger.info(f"✅ Saved {len(chunks)} chunks for document {document_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ DB error: {str(e)}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# ============================================
# EMBEDDING FUNCTIONS
# ============================================

def generate_embedding(text: str) -> list:
    """
    Generate embedding using Amazon Titan Embeddings
    Returns: list of 1024 floats
    """
    try:
        if not text or len(text.strip()) == 0:
            logger.warning("⚠️ Empty text provided for embedding")
            return None
            
        logger.info(f"🔮 Generating embedding for text: {text[:100]}...")
        
        model_id = "amazon.titan-embed-text-v2:0"
        
        body = json.dumps({
            "inputText": text,
            "dimensions": 1024,
            "normalize": True
        })
        
        logger.info(f"📤 Invoking Bedrock model: {model_id}")
        response = bedrock_runtime_client.invoke_model(
            modelId=model_id,
            body=body
        )
        
        response_body = json.loads(response['body'].read())
        embedding = response_body.get('embedding')
        
        if embedding:
            logger.info(f"✅ Generated embedding of size: {len(embedding)}")
            return embedding
        else:
            logger.error("❌ No embedding in response")
            return None
        
    except Exception as e:
        logger.error(f"❌ Embedding error: {str(e)}", exc_info=True)
        return None

def generate_embeddings_batch(texts: list) -> list:
    """
    Generate embeddings for multiple texts (batch)
    """
    embeddings = []
    for i, text in enumerate(texts):
        logger.info(f"📝 Processing chunk {i+1}/{len(texts)}")
        embedding = generate_embedding(text)
        embeddings.append(embedding)
    return embeddings

def store_embedding_in_db(document_id: str, chunk_id: str, embedding: list):
    """
    Store embedding vector in PostgreSQL
    """
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        vector_str = '[' + ','.join(map(str, embedding)) + ']'
        
        cursor.execute("""
            UPDATE chunks 
            SET embedding = %s::vector
            WHERE id = %s::uuid AND document_id = %s::uuid
        """, (vector_str, chunk_id, document_id))
        
        conn.commit()
        logger.info(f"✅ Stored embedding for chunk {chunk_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ DB error storing embedding: {str(e)}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def process_document_embeddings(document_id: str):
    """
    Generate and store embeddings for all chunks of a document
    """
    logger.info(f"🔮 Processing embeddings for document: {document_id}")
    
    chunks = get_chunks_by_document_db(document_id)
    
    if not chunks:
        logger.warning(f"⚠️ No chunks found for document {document_id}")
        return False
    
    logger.info(f"📊 Found {len(chunks)} chunks")
    
    texts = [chunk['text'] for chunk in chunks]
    chunk_ids = [chunk['id'] for chunk in chunks]
    
    embeddings = generate_embeddings_batch(texts)
    
    success_count = 0
    for i, (chunk_id, embedding) in enumerate(zip(chunk_ids, embeddings)):
        if embedding:
            if store_embedding_in_db(document_id, chunk_id, embedding):
                success_count += 1
    
    if success_count == len(chunks):
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE documents 
                    SET status = 'embedded'
                    WHERE id = %s::uuid
                """, (document_id,))
                conn.commit()
                logger.info(f"✅ Document {document_id} fully embedded")
            except Exception as e:
                logger.error(f"❌ Status update error: {str(e)}")
            finally:
                cursor.close()
                conn.close()
    
    return success_count == len(chunks)

# ============================================
# SEMANTIC SEARCH FUNCTIONS
# ============================================

def semantic_search(query: str, limit: int = 5) -> List[Dict]:
    """
    Search documents by meaning using vector similarity
    """
    logger.info(f"🔍 Semantic search: {query}")
    
    query_embedding = generate_embedding(query)
    if not query_embedding:
        return []
    
    vector_str = '[' + ','.join(map(str, query_embedding)) + ']'
    
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                d.id as document_id,
                d.filename,
                c.id as chunk_id,
                c.chunk_index,
                c.text,
                c.embedding <-> %s::vector as similarity_score
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <-> %s::vector
            LIMIT %s
        """, (vector_str, vector_str, limit))
        
        results = cursor.fetchall()
        
        search_results = []
        for row in results:
            search_results.append({
                'document_id': row[0],
                'filename': row[1],
                'chunk_id': row[2],
                'chunk_index': row[3],
                'text': row[4],
                'similarity_score': float(row[5]) if row[5] else None
            })
        
        logger.info(f"✅ Found {len(search_results)} results")
        return search_results
        
    except Exception as e:
        logger.error(f"❌ Search error: {str(e)}")
        return []
    finally:
        cursor.close()
        conn.close()

# ============================================
# RAG / TITAN FUNCTIONS
# ============================================

def generate_answer_with_titan(question: str, context_chunks: list) -> dict:
    """
    Generate an answer using Amazon Nova Pro
    """
    try:
        logger.info(f"🤖 Generating answer with Nova Pro for: {question}")
        
        # Prepare context from chunks
        context_text = "\n\n---\n\n".join([
            f"[Chunk {i+1}]\n{chunk['text']}"
            for i, chunk in enumerate(context_chunks)
        ])
        
        # Build prompt
        prompt = f"""Context:
{context_text}

Question: {question}

Answer based ONLY on the context above. If the answer is not in the context, say "I cannot find this information in the documents." Be concise and accurate.

Answer:"""
        
        # Use Nova Pro
        model_id = "amazon.nova-pro-v1:0"
        
        # Nova requires content as an array
        body = json.dumps({
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "inferenceConfig": {
                "max_new_tokens": 500,
                "temperature": 0.1,
                "top_p": 0.9
            }
        })
        
        # Call Bedrock
        response = bedrock_runtime_client.invoke_model(
            modelId=model_id,
            body=body
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        
        # Extract text from Nova response
        if 'output' in response_body and 'message' in response_body['output']:
            content = response_body['output']['message']['content']
            if isinstance(content, list) and len(content) > 0:
                answer = content[0].get('text', str(response_body))
            else:
                answer = str(response_body)
        else:
            answer = str(response_body)
        
        return {
            'answer': answer.strip(),
            'citations': [1]
        }
        
    except Exception as e:
        logger.error(f"❌ Nova error: {str(e)}", exc_info=True)
        return {
            'answer': f"Error: {str(e)}",
            'citations': []
        }

def rag_query(question: str, limit: int = 3) -> dict:
    """
    Full RAG pipeline: Search → Retrieve → Generate
    """
    logger.info(f"🔍 RAG Query: {question}")
    
    # Step 1: Semantic search
    search_results = semantic_search(question, limit)
    
    if not search_results:
        return {
            'question': question,
            'answer': 'No relevant documents found. Please upload documents first.',
            'citations': [],
            'sources': []
        }
    
    # Step 2: Format chunks for generation
    context_chunks = [
        {
            'text': result['text'],
            'document_id': result['document_id'],
            'filename': result['filename'],
            'chunk_index': result['chunk_index']
        }
        for result in search_results
    ]
    
    # Step 3: Generate answer with Titan
    try:
        result = generate_answer_with_titan(question, context_chunks)
    except Exception as e:
        logger.error(f"❌ Generation failed: {str(e)}")
        # Fallback: return the chunks without generation
        return {
            'question': question,
            'answer': f"Found {len(search_results)} relevant chunks. (Generation failed: {str(e)})",
            'citations': [],
            'sources': [
                {
                    'filename': chunk['filename'],
                    'chunk': chunk['chunk_index'],
                    'text_preview': chunk['text'][:200] + '...'
                }
                for chunk in context_chunks
            ],
            'chunks_used': len(context_chunks)
        }
    
    # Step 4: Add source info
    sources = [
        {
            'filename': chunk['filename'],
            'chunk': chunk['chunk_index'],
            'text_preview': chunk['text'][:200] + '...'
        }
        for chunk in context_chunks
    ]
    
    return {
        'question': question,
        'answer': result.get('answer', 'No answer generated'),
        'citations': result.get('citations', []),
        'sources': sources,
        'chunks_used': len(context_chunks)
    }

# ============================================
# HANDLER: CHAT / QUESTION ANSWERING
# ============================================
def handle_chat(event, context):
    """RAG-based question answering endpoint"""
    logger.info("--- CHAT / RAG QUERY ---")
    
    try:
        # Get query parameters
        query_params = event.get('queryStringParameters', {})
        question = query_params.get('q', '')
        limit = int(query_params.get('limit', 3))
        
        if not question:
            return create_response(400, {
                'error': 'Question parameter "q" is required',
                'example': '/chat?q=What+does+the+document+say+about+Amazon?'
            })
        
        # Run RAG query
        result = rag_query(question, limit)
        
        # Log result
        logger.info(f"✅ Answer generated: {result['answer'][:100]}...")
        
        return create_response(200, result)
        
    except Exception as e:
        logger.error(f"✗ Chat error: {str(e)}")
        return create_response(500, {'error': str(e)})

# ============================================
# HANDLER: S3 EVENT
# ============================================
def handle_s3_event(event, context):
    logger.info("--- PROCESSING S3 EVENT ---")
    results = []
    
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])
        
        if '/processed/' in key or '/chunks/' in key:
            logger.info(f"⏭️ Skipping processed file: {key}")
            continue
        
        logger.info(f"📁 Bucket: {bucket}")
        logger.info(f"📄 File: {key}")
        
        try:
            s3_response = s3_client.get_object(Bucket=bucket, Key=key)
            file_content = s3_response['Body'].read()
            file_size = len(file_content)
            
            logger.info(f"✅ Downloaded: {key} ({file_size} bytes)")
            
            text = extract_text_from_pdf(file_content)
            
            if not text:
                logger.warning("⚠️ No text extracted from PDF")
                results.append({
                    'bucket': bucket,
                    'key': key,
                    'status': 'warning',
                    'message': 'No text extracted'
                })
                continue
            
            chunks = chunk_text(text, chunk_size=500, overlap=100)
            
            filename = key.split('/')[-1]
            metadata = {
                's3_upload_date': datetime.now().isoformat(),
                'file_size': file_size,
                'file_type': 'pdf',
                'characters': len(text),
                'chunks': len(chunks)
            }
            
            doc_result = save_document_metadata(filename, key, metadata)
            
            if not doc_result:
                results.append({
                    'bucket': bucket,
                    'key': key,
                    'status': 'error',
                    'message': 'Failed to save document metadata'
                })
                continue
            
            doc_id = doc_result['id']
            success = save_chunks_to_db(doc_id, chunks)
            
            if success:
                logger.info(f"✅ Fully processed: {filename} ({len(chunks)} chunks)")
                results.append({
                    'bucket': bucket,
                    'key': key,
                    'size': file_size,
                    'chunks': len(chunks),
                    'document_id': doc_id,
                    'status': 'success'
                })
            else:
                results.append({
                    'bucket': bucket,
                    'key': key,
                    'status': 'error',
                    'message': 'Failed to save chunks'
                })
            
        except Exception as e:
            logger.error(f"✗ Error: {str(e)}")
            results.append({
                'bucket': bucket,
                'key': key,
                'status': 'error',
                'message': str(e)
            })
    
    return create_response(200, {
        'message': f'Processed {len(results)} files',
        'results': results
    })

# ============================================
# HANDLER: UPLOAD
# ============================================
def handle_upload(event, context):
    logger.info("--- PROCESSING FILE UPLOAD ---")
    
    try:
        body = event.get('body', '')
        is_base64 = event.get('isBase64Encoded', False)
        
        if not body:
            return create_response(400, {'error': 'No file uploaded'})
        
        if is_base64:
            file_data = base64.b64decode(body)
        else:
            file_data = body.encode('utf-8')
        
        query_params = event.get('queryStringParameters', {}) or {}
        filename = query_params.get('filename', f'upload_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf')
        
        if not filename.endswith('.pdf'):
            filename = filename + '.pdf'
        
        unique_id = str(uuid.uuid4())[:8]
        s3_key = f"uploads/{unique_id}_{filename}"
        
        logger.info(f"📄 Saving to S3: {s3_key}")
        logger.info(f"📊 File size: {len(file_data)} bytes")
        
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=file_data,
            ContentType='application/pdf'
        )
        
        logger.info(f"✅ Uploaded to S3: {s3_key}")
        
        metadata = {
            'uploaded_via': 'api',
            'file_size': len(file_data),
            'file_type': 'pdf'
        }
        doc_result = save_document_metadata(filename, s3_key, metadata)
        
        return create_response(200, {
            'message': 'File uploaded successfully',
            'file': filename,
            's3_key': s3_key,
            'bucket': S3_BUCKET,
            'document_id': doc_result['id'] if doc_result else None,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"✗ Upload error: {str(e)}", exc_info=True)
        return create_response(500, {'error': str(e)})

# ============================================
# HANDLER: LIST DOCUMENTS
# ============================================
def handle_list_documents(event, context):
    logger.info("--- LISTING DOCUMENTS ---")
    
    try:
        query_params = event.get('queryStringParameters', {}) or {}
        limit = int(query_params.get('limit', 50))
        offset = int(query_params.get('offset', 0))
        
        result = get_all_documents_db(limit, offset)
        
        logger.info(f"📊 Found {result['total']} documents")
        
        return create_response(200, result)
        
    except Exception as e:
        logger.error(f"✗ Error listing: {str(e)}", exc_info=True)
        return create_response(500, {'error': str(e)})

# ============================================
# HANDLER: GET DOCUMENT
# ============================================
def handle_get_document(event, context):
    logger.info("--- GET SPECIFIC DOCUMENT ---")
    
    try:
        path_params = event.get('pathParameters') or {}
        document_id = path_params.get('id', '')
        
        if not document_id:
            return create_response(400, {'error': 'Document ID is required'})
        
        logger.info(f"📄 Document ID: {document_id}")
        
        document = get_document_by_id_db(document_id)
        
        if not document:
            return create_response(404, {'error': f'Document {document_id} not found'})
        
        chunks = get_chunks_by_document_db(document_id)
        document['chunks'] = chunks
        document['chunk_count'] = len(chunks)
        
        return create_response(200, document)
        
    except Exception as e:
        logger.error(f"✗ Error: {str(e)}", exc_info=True)
        return create_response(500, {'error': str(e)})

# ============================================
# HANDLER: DELETE DOCUMENT
# ============================================
def handle_delete_document(event, context):
    logger.info("--- DELETE DOCUMENT ---")
    
    try:
        path_params = event.get('pathParameters') or {}
        document_id = path_params.get('id', '')
        
        if not document_id:
            return create_response(400, {'error': 'Document ID is required'})
        
        document = get_document_by_id_db(document_id)
        
        if not document:
            return create_response(404, {'error': f'Document {document_id} not found'})
        
        try:
            s3_client.delete_object(Bucket=S3_BUCKET, Key=document['s3_key'])
            logger.info(f"✅ Deleted from S3: {document['s3_key']}")
        except Exception as e:
            logger.warning(f"⚠️ Could not delete from S3: {str(e)}")
        
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM documents WHERE id = %s::uuid", (document_id,))
                conn.commit()
                logger.info(f"✅ Deleted document from DB: {document_id}")
            except Exception as e:
                logger.error(f"❌ DB delete error: {str(e)}")
                conn.rollback()
                return create_response(500, {'error': str(e)})
            finally:
                cursor.close()
                conn.close()
        
        return create_response(200, {
            'message': f'Document {document_id} deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"✗ Error: {str(e)}", exc_info=True)
        return create_response(500, {'error': str(e)})

# ============================================
# HANDLER: GET CHUNKS
# ============================================
def handle_get_chunks(event, context):
    logger.info("--- GET DOCUMENT CHUNKS ---")
    
    try:
        path_params = event.get('pathParameters') or {}
        document_id = path_params.get('id', '')
        
        if not document_id:
            return create_response(400, {'error': 'Document ID is required'})
        
        chunks = get_chunks_by_document_db(document_id)
        
        return create_response(200, {
            'document_id': document_id,
            'chunks': chunks,
            'count': len(chunks)
        })
        
    except Exception as e:
        logger.error(f"✗ Error: {str(e)}", exc_info=True)
        return create_response(500, {'error': str(e)})

# ============================================
# HANDLER: PROCESS EMBEDDINGS
# ============================================
def handle_process_embeddings(event, context):
    """Trigger embedding generation for a document"""
    logger.info("--- PROCESS EMBEDDINGS ---")
    
    try:
        path_params = event.get('pathParameters', {}) or {}
        document_id = path_params.get('id', '')
        
        if not document_id:
            return create_response(400, {'error': 'Document ID is required'})
        
        # Verify document exists
        doc = get_document_by_id_db(document_id)
        if not doc:
            return create_response(404, {'error': f'Document {document_id} not found'})
        
        # Process embeddings
        success = process_document_embeddings(document_id)
        
        if success:
            return create_response(200, {
                'message': 'Embeddings generated successfully',
                'document_id': document_id,
                'status': 'embedded'
            })
        else:
            return create_response(500, {
                'error': 'Failed to generate embeddings for some chunks',
                'document_id': document_id
            })
        
    except Exception as e:
        logger.error(f"✗ Error: {str(e)}", exc_info=True)
        return create_response(500, {'error': str(e)})

# ============================================
# HANDLER: PROCESS DOCUMENT
# ============================================
def handle_process_document(event, context):
    """Manually process a document from S3"""
    logger.info("--- MANUAL PROCESS DOCUMENT ---")
    
    try:
        path_params = event.get('pathParameters') or {}
        document_id = path_params.get('id', '')
        
        if not document_id:
            return create_response(400, {'error': 'Document ID is required'})
        
        # Get document from DB
        doc = get_document_by_id_db(document_id)
        if not doc:
            return create_response(404, {'error': f'Document {document_id} not found'})
        
        logger.info(f"📄 Processing: {doc['filename']} ({doc['s3_key']})")
        
        # Get file from S3
        try:
            s3_response = s3_client.get_object(Bucket=S3_BUCKET, Key=doc['s3_key'])
            file_content = s3_response['Body'].read()
            logger.info(f"✅ Downloaded {len(file_content)} bytes")
        except Exception as e:
            logger.error(f"❌ S3 download error: {str(e)}")
            return create_response(500, {'error': f'S3 download failed: {str(e)}'})
        
        # Extract text
        text = extract_text_from_pdf(file_content)
        if not text:
            return create_response(400, {'error': 'No text extracted from PDF'})
        
        logger.info(f"✅ Extracted {len(text)} characters")
        
        # Create chunks
        chunks = chunk_text(text, chunk_size=500, overlap=100)
        logger.info(f"✅ Created {len(chunks)} chunks")
        
        # Save chunks to DB
        success = save_chunks_to_db(document_id, chunks)
        
        if success:
            return create_response(200, {
                'message': 'Document processed successfully',
                'document_id': document_id,
                'filename': doc['filename'],
                'chunks': len(chunks),
                'status': 'processed'
            })
        else:
            return create_response(500, {'error': 'Failed to save chunks to database'})
        
    except Exception as e:
        logger.error(f"✗ Error: {str(e)}", exc_info=True)
        return create_response(500, {'error': str(e)})

# ============================================
# HANDLER: SEMANTIC SEARCH
# ============================================
def handle_search(event, context):
    """Semantic search endpoint"""
    logger.info("--- SEMANTIC SEARCH ---")
    
    try:
        query_params = event.get('queryStringParameters', {}) or {}
        query = query_params.get('q', '')
        limit = int(query_params.get('limit', 5))
        
        if not query:
            return create_response(400, {'error': 'Query parameter "q" is required'})
        
        results = semantic_search(query, limit)
        
        return create_response(200, {
            'query': query,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        logger.error(f"✗ Search error: {str(e)}", exc_info=True)
        return create_response(500, {'error': str(e)})

# ============================================
# HANDLER: HELLO
# ============================================
def handle_hello(event, context):
    logger.info("--- HELLO ENDPOINT ---")
    
    query_params = event.get('queryStringParameters', {}) or {}
    name = query_params.get('name', 'World')
    
    conn = get_db_connection()
    db_status = "Connected" if conn else "Failed"
    if conn:
        conn.close()
    
    bedrock_status = "Available"
    bedrock_error = None
    try:
        response = bedrock_client.list_foundation_models()
        logger.info("✅ Bedrock is available")
    except Exception as e:
        bedrock_status = "Error"
        bedrock_error = str(e)
        logger.error(f"❌ Bedrock error: {str(e)}", exc_info=True)
    
    response_body = {
        'message': f'Hello {name}!',
        'timestamp': datetime.now().isoformat(),
        'api_version': '4.0.0',
        'database_status': db_status,
        'bedrock_status': bedrock_status,
        'available_endpoints': [
            'GET /hello?name=YourName',
            'POST /upload?filename=file.pdf',
            'GET /documents?limit=50&offset=0',
            'GET /document/{id}',
            'DELETE /document/{id}',
            'GET /document/{id}/chunks',
            'POST /document/{id}/embed',
            'GET /search?q=your+query&limit=5',
            'GET /chat?q=your+question&limit=3',
            'POST /document/{id}/process',
            'GET /init-db',
            'GET /test-db'
        ]
    }
    
    if bedrock_error:
        response_body['bedrock_error'] = bedrock_error
    
    return create_response(200, response_body)

# ============================================
# DATABASE INITIALIZATION
# ============================================
def initialize_database():
    """Create database and tables if they don't exist"""
    try:
        conn = pg8000.connect(
            host=DB_HOST,
            port=DB_PORT,
            database='postgres',
            user=DB_USER,
            password=DB_PASSWORD,
            timeout=10
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'documents_db'")
        if not cursor.fetchone():
            logger.info("📦 Creating documents_db...")
            cursor.execute("CREATE DATABASE documents_db")
            logger.info("✅ Created documents_db")
        
        cursor.close()
        conn.close()
        
        conn = pg8000.connect(
            host=DB_HOST,
            port=DB_PORT,
            database='documents_db',
            user=DB_USER,
            password=DB_PASSWORD,
            timeout=10
        )
        cursor = conn.cursor()
        
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                filename VARCHAR(255),
                s3_key VARCHAR(512),
                metadata JSONB,
                status VARCHAR(50) DEFAULT 'uploaded',
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_chunks INTEGER DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                chunk_index INTEGER,
                text TEXT,
                token_count INTEGER,
                embedding vector(1024),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops)")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info("✅ Database initialization complete")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database initialization error: {str(e)}", exc_info=True)
        return False

# ============================================
# HANDLER: INITIALIZE DB
# ============================================
def handle_init_db(event, context):
    """Initialize database and tables"""
    logger.info("--- INITIALIZE DATABASE ---")
    
    success = initialize_database()
    
    if success:
        return create_response(200, {
            'status': 'success',
            'message': 'Database initialized successfully',
            'tables': ['documents', 'chunks']
        })
    else:
        return create_response(500, {
            'status': 'error',
            'message': 'Database initialization failed'
        })

# ============================================
# HANDLER: TEST DATABASE
# ============================================
def handle_test_db(event, context):
    logger.info("--- TEST DATABASE ---")
    
    try:
        conn = get_db_connection()
        if not conn:
            return create_response(500, {
                'status': 'error',
                'message': 'Database connection failed'
            })
        
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        return create_response(200, {
            'status': 'success',
            'message': 'Database connected',
            'version': version,
            'database': DB_NAME
        })
        
    except Exception as e:
        logger.error(f"✗ Error: {str(e)}", exc_info=True)
        return create_response(500, {'error': str(e)})

# ============================================
# MAIN LAMBDA HANDLER
# ============================================
def lambda_handler(event, context):
    logger.info("=" * 60)
    logger.info(f"LAMBDA EXECUTION STARTED - Request ID: {context.aws_request_id}")
    logger.info(f"Event: {json.dumps(event, default=str)}")
    
    try:
        if 'Records' in event and event['Records'] and 's3' in event['Records'][0]:
            return handle_s3_event(event, context)
        
        http_method = event.get('httpMethod', 'GET')
        if http_method == 'OPTIONS':
            return create_response(200, {})
        
        path = event.get('path', '/')
        logger.info(f"HTTP Method: {http_method}, Path: {path}")
        
        # === ROUTING ===
        if path == '/upload' and http_method == 'POST':
            return handle_upload(event, context)
        elif path == '/documents' and http_method == 'GET':
            return handle_list_documents(event, context)
        elif path == '/hello' and http_method == 'GET':
            return handle_hello(event, context)
        elif path.startswith('/document/') and path.endswith('/chunks') and http_method == 'GET':
            parts = path.split('/')
            if len(parts) >= 3:
                event['pathParameters'] = {'id': parts[2]}
            return handle_get_chunks(event, context)
        elif path.startswith('/document/') and path.endswith('/embed') and http_method == 'POST':
            parts = path.split('/')
            if len(parts) >= 3:
                event['pathParameters'] = {'id': parts[2]}
            return handle_process_embeddings(event, context)
        elif path.startswith('/document/') and path.endswith('/process') and http_method == 'POST':
            parts = path.split('/')
            if len(parts) >= 3:
                event['pathParameters'] = {'id': parts[2]}
            return handle_process_document(event, context)
        elif path == '/search' and http_method == 'GET':
            return handle_search(event, context)
        elif path == '/chat' and http_method in ['GET', 'POST']:
            return handle_chat(event, context)
        elif path.startswith('/document/') and http_method == 'GET':
            parts = path.split('/')
            if len(parts) >= 3:
                event['pathParameters'] = {'id': parts[2]}
            return handle_get_document(event, context)
        elif path.startswith('/document/') and http_method == 'DELETE':
            parts = path.split('/')
            if len(parts) >= 3:
                event['pathParameters'] = {'id': parts[2]}
            return handle_delete_document(event, context)
        elif path == '/init-db' and http_method == 'GET':
            return handle_init_db(event, context)
        elif path == '/test-db' and http_method == 'GET':
            return handle_test_db(event, context)
        else:
            return create_response(404, {'error': f'Path {path} not found'})
        
    except Exception as e:
        logger.error(f"ERROR: {str(e)}", exc_info=True)
        return create_response(500, {'error': str(e)})