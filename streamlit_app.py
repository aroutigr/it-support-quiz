import streamlit as st
import json
import os
import random
from datetime import datetime
from anthropic import Anthropic

# ==========================================
# CONFIGURATION
# ==========================================
API_KEY = st.secrets["ANTHROPIC_API_KEY"]
AI_MODEL = "claude-sonnet-4-5-20250929"
QUESTIONS_PER_QUIZ = 10 
COMPETENCY_ID = "IT-SUPPORT-01"

# ==========================================
# HELPER FUNCTIONS (Logic adapted from main_v9)
# ==========================================

def get_client():
    return Anthropic(api_key=API_KEY)

def randomize_question(q):
    """Shuffles options and updates correct answer index."""
    raw_options = []
    for opt in q["options"]:
        # Strip "A) " prefix if present
        if len(opt) > 3 and opt[1:3] == ") ": 
            raw_options.append(opt[3:])
        else:
            raw_options.append(opt)
    
    # Identify correct text
    if len(q["correct_answer"]) == 1:
        correct_index = ord(q["correct_answer"]) - 65 
        if 0 <= correct_index < len(raw_options):
            correct_text = raw_options[correct_index]
        else:
            return q 
    else:
        return q

    random.shuffle(raw_options)
    
    # Find new correct index
    new_correct_index = raw_options.index(correct_text)
    new_correct_letter = chr(65 + new_correct_index) 
    
    # Re-attach prefixes
    new_options = [f"{chr(65+i)}) {opt}" for i, opt in enumerate(raw_options)]
    
    return {
        "id": q["id"],
        "question": q["question"],
        "options": new_options,
        "correct_answer": new_correct_letter,
        "explanation": q.get("explanation", "")
    }

def load_questions(competency, concept, filename="questions.json"):
    if not os.path.exists(filename): return []
    try:
        with open(filename, 'r') as f:
            db = json.load(f)
        return db.get(competency, {}).get(concept, [])
    except:
        return []

def save_questions_to_file(questions, competency, concept, filename="questions.json"):
    db = {}
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f: db = json.load(f)
        except: db = {}

    if competency not in db: db[competency] = {}
    if concept not in db[competency]: db[competency][concept] = []

    for q in questions:
        q["origin"] = "ai"
        q["date_generated"] = datetime.now().strftime("%Y-%m-%d")
        db[competency][concept].append(q)

    with open(filename, 'w') as f:
        json.dump(db, f, indent=4)

def generate_quiz_two(competency, concept, prev_questions):
    """Generates variations of previous questions."""
    client = get_client()
    
    history_text = "\n".join([f"{i+1}. {q['question']}" for i, q in enumerate(prev_questions)])
    
    prompt = f"""Competency: {competency}
Concept: {concept}

PREVIOUS QUESTIONS SEEN BY STUDENT:
{history_text}

TASK: Generate {len(prev_questions)} NEW multiple-choice questions.
IMPORTANT: These must be VARIATIONS or ADVANCED APPLICATIONS of the questions above.
- If Previous Q1 was about RDP, New Q1 must be about RDP (different scenario).
- Keep difficulty similar or slightly higher.

Format strictly as a JSON list of objects:
[
  {{
    "id": 1,
    "question": "Question text?",
    "options": ["A) Option", "B) Option", "C) Option", "D) Option"],
    "correct_answer": "A",
    "explanation": "Brief explanation"
  }}
]"""

    try:
        message = client.messages.create(
            model=AI_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        clean_json = message.content[0].text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"AI Generation Error: {e}")
        return []

def get_ai_feedback(competency, concept, q1_data, q1_results, q2_data, q2_results):
    client = get_client()
    
    def format_log(questions, results):
        txt = ""
        for q, res in zip(questions, results):
            status = "CORRECT" if res['is_correct'] else "INCORRECT"
            txt += f"- Q: {q['question']}\n  Student: {res['student_answer']} | Correct: {q['correct_answer']} -> {status}\n"
        return txt

    prompt = f"""You are an IT Instructor.
    Context: {concept}
    
    --- QUIZ 1 (Baseline) ---
    {format_log(q1_data, q1_results)}
    
    --- QUIZ 2 (Reinforcement) ---
    {format_log(q2_data, q2_results)}
    
    Task:
    1. Did the student improve?
    2. Identify 1 specific concept they struggle with.
    3. Provide 2 short study tips.
    Address the student directly.
    """
    
    try:
        message = client.messages.create(model=AI_MODEL, max_tokens=1024, messages=[{"role": "user", "content": prompt}])
        return message.content[0].text
    except Exception as e:
        return f"Feedback unavailable: {e}"

# ==========================================
# STREAMLIT UI
# ==========================================

st.set_page_config(page_title="AI IT Support for evaluation", layout="centered")

# Initialize Session State
if 'step' not in st.session_state: st.session_state.step = 1
if 'q1_questions' not in st.session_state: st.session_state.q1_questions = []
if 'q2_questions' not in st.session_state: st.session_state.q2_questions = []
if 'q1_score' not in st.session_state: st.session_state.q1_score = 0
if 'q2_score' not in st.session_state: st.session_state.q2_score = 0
if 'q1_results' not in st.session_state: st.session_state.q1_results = []
if 'q2_results' not in st.session_state: st.session_state.q2_results = []

# --- HEADER ---
st.title("🎓 AI-Powered IT Support for evaluation")
st.markdown("---")

# --- STEP 1: CONFIGURATION ---
if st.session_state.step == 1:
    st.subheader("Student Registration")
    
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Name", value="Student")
    with col2:
        group = st.text_input("Group", value="Vocational A")
        
    concepts = [
        "Remote Access Tools", 
        "Troubleshooting Methods", 
        "Customer Communication", 
        "Ticket Management"
    ]
    concept = st.selectbox("Select Learning Concept", concepts)
    
    if st.button("Start Assessment"):
        st.session_state.name = name
        st.session_state.group = group
        st.session_state.concept = concept
        
        # Load and Randomize Q1 immediately
        raw_questions = load_questions(COMPETENCY_ID, concept)
        # Randomize logic
        shuffled_q1 = []
        for q in raw_questions[:QUESTIONS_PER_QUIZ]:
            shuffled_q1.append(randomize_question(q))
            
        st.session_state.q1_questions = shuffled_q1
        st.session_state.step = 2
        st.rerun()

# --- STEP 2: QUIZ ONE ---
elif st.session_state.step == 2:
    st.subheader(f"Quiz 1: {st.session_state.concept} (Baseline)")
    
    if not st.session_state.q1_questions:
        st.warning("No questions found in database. Generating entirely via AI...")
        # Fallback logic could go here, but for now we warn
    
    with st.form("quiz_one_form"):
        user_answers = {}
        for i, q in enumerate(st.session_state.q1_questions):
            st.markdown(f"**Q{i+1}: {q['question']}**")
            user_answers[i] = st.radio(
                "Select Answer:", 
                q['options'], 
                key=f"q1_{i}", 
                label_visibility="collapsed"
            )
            st.markdown("---")
            
        submitted = st.form_submit_button("Submit Baseline Quiz")
        
        if submitted:
            score = 0
            results = []
            
            # Grade it
            for i, q in enumerate(st.session_state.q1_questions):
                selected = user_answers[i].split(")")[0] # Extract "A" from "A) Text"
                correct = q['correct_answer']
                is_correct = selected == correct
                if is_correct: score += 1
                results.append({
                    "student_answer": selected,
                    "is_correct": is_correct
                })
            
            st.session_state.q1_score = score
            st.session_state.q1_results = results
            st.session_state.step = 3
            st.rerun()

# --- STEP 3: FEEDBACK & TRANSITION ---
elif st.session_state.step == 3:
    st.subheader("Quiz 1 Results")
    st.info(f"You scored: {st.session_state.q1_score} / {len(st.session_state.q1_questions)}")
    
    # Show detailed feedback
    for i, (q, res) in enumerate(zip(st.session_state.q1_questions, st.session_state.q1_results)):
        with st.expander(f"Question {i+1} Details"):
            st.write(f"**Question:** {q['question']}")
            if res['is_correct']:
                st.success(f"✅ Correct! ({q['correct_answer']})")
            else:
                st.error(f"❌ Incorrect. You picked {res['student_answer']}, correct was {q['correct_answer']}.")
            st.write(f"*Explanation: {q['explanation']}*")

    st.markdown("### Next Step: AI Reinforcement")
    st.write("The AI is now analyzing your answers to generate a custom follow-up quiz.")
    
    if st.button("Generate Quiz 2"):
        st.session_state.step = 4
        st.rerun()

# --- STEP 4: GENERATE QUIZ 2 ---
elif st.session_state.step == 4:
    with st.spinner('🤖 AI is generating variations of your baseline questions...'):
        # Generate Q2 based on Q1
        new_questions = generate_quiz_two(
            COMPETENCY_ID, 
            st.session_state.concept, 
            st.session_state.q1_questions
        )
        
        # Randomize them immediately
        shuffled_q2 = []
        for q in new_questions:
            shuffled_q2.append(randomize_question(q))
            
        st.session_state.q2_questions = shuffled_q2
        
        # Save to DB
        save_questions_to_file(new_questions, COMPETENCY_ID, st.session_state.concept)
        
        st.session_state.step = 5
        st.rerun()

# --- STEP 5: QUIZ TWO ---
elif st.session_state.step == 5:
    st.subheader(f"Quiz 2: {st.session_state.concept} (Reinforcement)")
    st.info("These questions are variations of the ones you just took. Apply what you learned!")
    
    with st.form("quiz_two_form"):
        user_answers_2 = {}
        for i, q in enumerate(st.session_state.q2_questions):
            st.markdown(f"**Q{i+1}: {q['question']}**")
            user_answers_2[i] = st.radio(
                "Select Answer:", 
                q['options'], 
                key=f"q2_{i}", 
                label_visibility="collapsed"
            )
            st.markdown("---")
            
        submitted_2 = st.form_submit_button("Submit Reinforcement Quiz")
        
        if submitted_2:
            score = 0
            results = []
            for i, q in enumerate(st.session_state.q2_questions):
                selected = user_answers_2[i].split(")")[0]
                correct = q['correct_answer']
                is_correct = selected == correct
                if is_correct: score += 1
                results.append({
                    "student_answer": selected,
                    "is_correct": is_correct
                })
            
            st.session_state.q2_score = score
            st.session_state.q2_results = results
            st.session_state.step = 6
            st.rerun()

# --- STEP 6: FINAL ANALYSIS ---
elif st.session_state.step == 6:
    st.subheader("🏆 Final Performance Analysis")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Baseline Score", f"{st.session_state.q1_score}/{len(st.session_state.q1_questions)}")
    with col2:
        delta = st.session_state.q2_score - st.session_state.q1_score
        st.metric("Reinforcement Score", f"{st.session_state.q2_score}/{len(st.session_state.q2_questions)}", delta=delta)

    st.markdown("---")
    st.subheader("🤖 AI Evaluation Feedback")
    
    with st.spinner("Analyzing improvement..."):
        feedback = get_ai_feedback(
            COMPETENCY_ID,
            st.session_state.concept,
            st.session_state.q1_questions,
            st.session_state.q1_results,
            st.session_state.q2_questions,
            st.session_state.q2_results
        )
        st.success(feedback)
        
    if st.button("Start New Session"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()