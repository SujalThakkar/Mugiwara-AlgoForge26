"""
Budget Bandhu Test Dashboard
Interactive testing interface for the ML chatbot and memory system.

Features:
- Live chat with Budget Bandhu AI
- Add/view user memories (semantic + episodic)
- View model stats and performance
- Test context-aware responses

Run: python dashboard.py
Then open: http://localhost:5000

Author: Aryan Lomte
Date: Jan 16, 2026
"""
import sys
sys.path.append('.')

from flask import Flask, render_template_string, request, jsonify
import os

from core.memory_system import MemorySystem
from intelligence.phi3_rag import Phi3RAG
from core.gating import GatingSystem
from core.agent_controller import AgentController

app = Flask(__name__)

# Initialize components
print("[DASHBOARD] Initializing components...")
DB_PATH = "dashboard_test.db"

# Clean start for testing
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print(f"[DASHBOARD] Cleaned old database: {DB_PATH}")

memory = MemorySystem(db_path=DB_PATH)
phi3 = Phi3RAG()
gating = GatingSystem()
agent = AgentController(memory_system=memory, phi3_rag=phi3, gating_system=gating)

# Default test user
DEFAULT_USER_ID = 1

# HTML Template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Budget Bandhu - Test Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        header {
            text-align: center;
            padding: 20px 0;
            border-bottom: 1px solid #333;
            margin-bottom: 20px;
        }
        
        header h1 {
            font-size: 2rem;
            background: linear-gradient(90deg, #00d4ff, #7c3aed);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        header p {
            color: #888;
            margin-top: 5px;
        }
        
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        
        @media (max-width: 900px) {
            .grid { grid-template-columns: 1fr; }
        }
        
        .card {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #333;
        }
        
        .card h2 {
            color: #00d4ff;
            margin-bottom: 15px;
            font-size: 1.2rem;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        /* Chat Section */
        #chat-messages {
            height: 300px;
            overflow-y: auto;
            background: #0a0a14;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
        }
        
        .message {
            margin-bottom: 12px;
            padding: 10px 15px;
            border-radius: 12px;
            max-width: 85%;
        }
        
        .message.user {
            background: #7c3aed;
            margin-left: auto;
        }
        
        .message.bot {
            background: #1e3a5f;
        }
        
        .message .meta {
            font-size: 0.75rem;
            color: #888;
            margin-top: 5px;
        }
        
        #chat-input {
            display: flex;
            gap: 10px;
        }
        
        #chat-input input {
            flex: 1;
            padding: 12px 15px;
            border-radius: 8px;
            border: 1px solid #444;
            background: #1a1a2e;
            color: #fff;
            font-size: 1rem;
        }
        
        #chat-input input:focus {
            outline: none;
            border-color: #00d4ff;
        }
        
        button {
            padding: 12px 24px;
            border-radius: 8px;
            border: none;
            background: linear-gradient(90deg, #00d4ff, #7c3aed);
            color: #fff;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s, opacity 0.2s;
        }
        
        button:hover {
            transform: translateY(-2px);
            opacity: 0.9;
        }
        
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        /* Memory Section */
        .memory-form {
            margin-bottom: 15px;
        }
        
        .memory-form label {
            display: block;
            margin-bottom: 5px;
            color: #888;
            font-size: 0.9rem;
        }
        
        .memory-form input, .memory-form select {
            width: 100%;
            padding: 10px;
            border-radius: 6px;
            border: 1px solid #444;
            background: #1a1a2e;
            color: #fff;
            margin-bottom: 10px;
        }
        
        .memory-list {
            max-height: 200px;
            overflow-y: auto;
            background: #0a0a14;
            border-radius: 8px;
            padding: 10px;
        }
        
        .memory-item {
            padding: 8px 12px;
            background: #1e293b;
            border-radius: 6px;
            margin-bottom: 8px;
            font-size: 0.9rem;
        }
        
        .memory-item .type {
            color: #00d4ff;
            font-weight: bold;
        }
        
        /* Stats Section */
        .stat-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
        }
        
        .stat-box {
            background: #0a0a14;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        
        .stat-box .value {
            font-size: 1.8rem;
            font-weight: bold;
            color: #00d4ff;
        }
        
        .stat-box .label {
            color: #888;
            font-size: 0.85rem;
            margin-top: 5px;
        }
        
        /* User Section */
        .user-info {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
        }
        
        .user-info input {
            width: 100px;
            padding: 8px;
            border-radius: 6px;
            border: 1px solid #444;
            background: #1a1a2e;
            color: #fff;
            text-align: center;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid #333;
            border-top-color: #00d4ff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .success { color: #10b981; }
        .error { color: #ef4444; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🤖 Budget Bandhu Test Dashboard</h1>
            <p>ML Chatbot Testing Interface | Memory System | Agent Controller</p>
        </header>
        
        <div class="grid">
            <!-- Chat Section -->
            <div class="card">
                <h2>💬 Chat with Budget Bandhu</h2>
                
                <div class="user-info">
                    <span>User ID:</span>
                    <input type="number" id="user-id" value="1" min="1">
                    <button onclick="refreshMemory()" style="padding: 8px 16px;">Refresh Memory</button>
                </div>
                
                <div id="chat-messages">
                    <div class="message bot">
                        <div>Namaste! I'm Budget Bandhu, your AI financial assistant. How can I help you today? 🙏</div>
                        <div class="meta">System • Ready</div>
                    </div>
                </div>
                
                <div id="chat-input">
                    <input type="text" id="query" placeholder="Ask about budgeting, savings, taxes..." 
                           onkeypress="if(event.key==='Enter') sendMessage()">
                    <button onclick="sendMessage()" id="send-btn">Send</button>
                </div>
            </div>
            
            <!-- Memory Management -->
            <div class="card">
                <h2>🧠 Memory Management</h2>
                
                <!-- Add Semantic Memory -->
                <div class="memory-form">
                    <h3 style="color:#7c3aed; margin-bottom:10px;">Add User Profile (Semantic)</h3>
                    <label>Attribute Type</label>
                    <select id="sem-type">
                        <option value="monthly_income">Monthly Income</option>
                        <option value="risk_profile">Risk Profile</option>
                        <option value="savings_goal">Savings Goal</option>
                        <option value="expense_pattern">Expense Pattern</option>
                        <option value="investment_preference">Investment Preference</option>
                    </select>
                    <label>Value</label>
                    <input type="text" id="sem-value" placeholder="e.g., ₹50,000/month">
                    <button onclick="addSemanticMemory()">Add Profile</button>
                </div>
                
                <!-- Add Episodic Memory -->
                <div class="memory-form">
                    <h3 style="color:#10b981; margin-bottom:10px;">Add Recent Event (Episodic)</h3>
                    <label>Trigger Type</label>
                    <select id="epi-trigger">
                        <option value="overspend">Overspend</option>
                        <option value="goal_event">Goal Event</option>
                        <option value="bill_prediction">Bill Prediction</option>
                        <option value="savings_milestone">Savings Milestone</option>
                    </select>
                    <label>Event Summary</label>
                    <input type="text" id="epi-summary" placeholder="e.g., Overspent on dining by ₹3,000">
                    <button onclick="addEpisodicMemory()">Add Event</button>
                </div>
                
                <!-- Current Memory -->
                <h3 style="margin-top:20px; margin-bottom:10px;">📋 Current Memory</h3>
                <div class="memory-list" id="memory-list">
                    <div style="color:#888;">No memories yet. Add some above!</div>
                </div>
            </div>
            
            <!-- Stats Section -->
            <div class="card">
                <h2>📊 Model Statistics</h2>
                <div class="stat-grid">
                    <div class="stat-box">
                        <div class="value" id="stat-requests">0</div>
                        <div class="label">Total Requests</div>
                    </div>
                    <div class="stat-box">
                        <div class="value" id="stat-errors">0</div>
                        <div class="label">Errors</div>
                    </div>
                    <div class="stat-box">
                        <div class="value" id="stat-latency">0.0s</div>
                        <div class="label">Avg Latency</div>
                    </div>
                    <div class="stat-box">
                        <div class="value" id="stat-model">-</div>
                        <div class="label">Model</div>
                    </div>
                </div>
                <button onclick="refreshStats()" style="margin-top:15px; width:100%;">Refresh Stats</button>
            </div>
            
            <!-- Quick Test Queries -->
            <div class="card">
                <h2>🚀 Quick Test Queries</h2>
                <div style="display:flex; flex-direction:column; gap:10px;">
                    <button onclick="testQuery('How should I track my monthly expenses?')" 
                            style="text-align:left; padding:10px 15px;">
                        💡 How should I track my monthly expenses?
                    </button>
                    <button onclick="testQuery('What are the tax benefits under Section 80C?')"
                            style="text-align:left; padding:10px 15px;">
                        📋 Tax benefits under Section 80C?
                    </button>
                    <button onclick="testQuery('Suggest ways to save ₹10,000 per month')"
                            style="text-align:left; padding:10px 15px;">
                        💰 Suggest ways to save ₹10,000/month
                    </button>
                    <button onclick="testQuery('Can I afford a ₹15,000 laptop?')"
                            style="text-align:left; padding:10px 15px;">
                        💻 Can I afford a ₹15,000 laptop?
                    </button>
                    <button onclick="testQuery('What is budgeting?')"
                            style="text-align:left; padding:10px 15px;">
                        📖 What is budgeting?
                    </button>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        function getUserId() {
            return parseInt(document.getElementById('user-id').value) || 1;
        }
        
        function addMessage(content, isUser, meta = '') {
            const messages = document.getElementById('chat-messages');
            const div = document.createElement('div');
            div.className = `message ${isUser ? 'user' : 'bot'}`;
            div.innerHTML = `<div>${content}</div><div class="meta">${meta}</div>`;
            messages.appendChild(div);
            messages.scrollTop = messages.scrollHeight;
        }
        
        async function sendMessage() {
            const input = document.getElementById('query');
            const query = input.value.trim();
            if (!query) return;
            
            const btn = document.getElementById('send-btn');
            btn.disabled = true;
            btn.innerHTML = '<span class="loading"></span>';
            
            addMessage(query, true, 'You');
            input.value = '';
            
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({query, user_id: getUserId()})
                });
                
                const data = await response.json();
                
                if (data.error) {
                    addMessage(`Error: ${data.error}`, false, 'System Error');
                } else {
                    const meta = `Budget Bandhu • ${data.confidence.toFixed(2)} confidence • ${data.memory_used.episodic_count}E/${data.memory_used.semantic_count}S memories`;
                    addMessage(data.response, false, meta);
                }
                
                refreshStats();
                refreshMemory();
                
            } catch (err) {
                addMessage(`Connection error: ${err.message}`, false, 'Error');
            }
            
            btn.disabled = false;
            btn.textContent = 'Send';
        }
        
        function testQuery(query) {
            document.getElementById('query').value = query;
            sendMessage();
        }
        
        async function addSemanticMemory() {
            const attrType = document.getElementById('sem-type').value;
            const value = document.getElementById('sem-value').value.trim();
            if (!value) return alert('Please enter a value');
            
            try {
                const response = await fetch('/memory/semantic', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_id: getUserId(), attribute_type: attrType, value})
                });
                
                const data = await response.json();
                if (data.success) {
                    document.getElementById('sem-value').value = '';
                    refreshMemory();
                }
            } catch (err) {
                alert('Error adding memory');
            }
        }
        
        async function addEpisodicMemory() {
            const trigger = document.getElementById('epi-trigger').value;
            const summary = document.getElementById('epi-summary').value.trim();
            if (!summary) return alert('Please enter an event summary');
            
            try {
                const response = await fetch('/memory/episodic', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_id: getUserId(), trigger_type: trigger, event_summary: summary})
                });
                
                const data = await response.json();
                if (data.success) {
                    document.getElementById('epi-summary').value = '';
                    refreshMemory();
                }
            } catch (err) {
                alert('Error adding memory');
            }
        }
        
        async function refreshMemory() {
            try {
                const response = await fetch(`/memory/${getUserId()}`);
                const data = await response.json();
                
                const list = document.getElementById('memory-list');
                if (data.total === 0) {
                    list.innerHTML = '<div style="color:#888;">No memories yet. Add some above!</div>';
                    return;
                }
                
                let html = '';
                
                if (data.semantic.length) {
                    html += '<div style="color:#7c3aed; font-weight:bold; margin-bottom:8px;">User Profile:</div>';
                    data.semantic.forEach(m => {
                        html += `<div class="memory-item"><span class="type">${m.attribute_type}:</span> ${m.value}</div>`;
                    });
                }
                
                if (data.episodic.length) {
                    html += '<div style="color:#10b981; font-weight:bold; margin:15px 0 8px;">Recent Events:</div>';
                    data.episodic.forEach(m => {
                        html += `<div class="memory-item"><span class="type">[${m.trigger_type}]</span> ${m.event_summary}</div>`;
                    });
                }
                
                list.innerHTML = html;
                
            } catch (err) {
                console.error('Error refreshing memory:', err);
            }
        }
        
        async function refreshStats() {
            try {
                const response = await fetch('/stats');
                const data = await response.json();
                
                document.getElementById('stat-requests').textContent = data.total_requests;
                document.getElementById('stat-errors').textContent = data.total_errors;
                document.getElementById('stat-latency').textContent = `${data.avg_latency_seconds.toFixed(2)}s`;
                document.getElementById('stat-model').textContent = data.model;
                
            } catch (err) {
                console.error('Error refreshing stats:', err);
            }
        }
        
        // Initial load
        refreshStats();
        refreshMemory();
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    query = data.get('query', '')
    user_id = data.get('user_id', DEFAULT_USER_ID)
    
    try:
        result = agent.execute_turn(
            user_id=user_id,
            query=query,
            session_context={}
        )
        
        return jsonify({
            'response': result['response'],
            'confidence': result['confidence'],
            'memory_used': result['memory_used'],
            'gates_passed': result['gates_passed'],
            'explanation': result.get('explanation', '')
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/memory/<int:user_id>')
def get_memory(user_id):
    context = memory.retrieve_context(user_id, "")
    return jsonify({
        'semantic': context['semantic'],
        'episodic': context['episodic'],
        'total': context['total_retrieved']
    })

@app.route('/memory/semantic', methods=['POST'])
def add_semantic():
    data = request.json
    user_id = data.get('user_id', DEFAULT_USER_ID)
    
    memory_id = memory.store_semantic(user_id, {
        'attribute_type': data.get('attribute_type'),
        'value': data.get('value'),
        'confidence': 0.9
    })
    
    return jsonify({'success': True, 'id': memory_id})

@app.route('/memory/episodic', methods=['POST'])
def add_episodic():
    data = request.json
    user_id = data.get('user_id', DEFAULT_USER_ID)
    
    memory_id = memory.store_episodic(user_id, {
        'trigger_type': data.get('trigger_type'),
        'event_summary': data.get('event_summary'),
        'interpretation': 'User-added event',
        'behavioral_effect': 'Consider in future advice',
        'confidence_score': 0.85
    })
    
    return jsonify({'success': True, 'id': memory_id})

@app.route('/stats')
def get_stats():
    return jsonify(phi3.get_stats())

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 BUDGET BANDHU TEST DASHBOARD")
    print("="*60)
    print(f"📊 Database: {DB_PATH}")
    print(f"🤖 Model: {phi3.model_name}")
    print(f"🌐 URL: http://localhost:5000")
    print("="*60 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=5000)
