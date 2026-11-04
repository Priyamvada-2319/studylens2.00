import os
from io import BytesIO
import pandas as pd
import plotly.express as px
import streamlit as st
from core import engine as en, storage as db

st.set_page_config(page_title='StudyLens AI 2.0', page_icon='🎓', layout='wide')
db.init()
st.title('🎓 StudyLens AI 2.0')
st.caption('Diagnose · Plan · Practise · Improve — Gemini cloud AI, no Ollama')

def secret(name, default=''):
    try:
        return str(st.secrets.get(name, os.getenv(name, default)))
    except Exception:
        return os.getenv(name, default)

for key, val in {'quiz': [], 'results': None, 'source_text': '', 'references': [], 'quiz_key': ''}.items():
    if key not in st.session_state:
        st.session_state[key] = val

with st.sidebar:
    st.header('Your preparation')
    demo_id = st.text_input('Demo identifier (not a password)', 'Exhibition Guest').strip() or 'Exhibition Guest'
    exam = st.selectbox('Preparation domain', en.EXAMS, index=en.EXAMS.index('ISC Boards'))
    if exam == 'Other / Custom':
        exam = st.text_input('Specify examination', 'School examination')
    grade = st.selectbox('Level', ['Class 8', 'Class 9', 'Class 10', 'Class 11', 'Class 12', 'Graduation', 'Other'], index=3)
    section = st.radio('Navigate', ['🏠 Overview', '📝 Diagnostic Test', '📊 My Diagnostics', '🗓️ Study Planner', '🃏 Flashcards', '✅ Revision Tracker', '🎞️ Learning Reels', '💬 Concept Coach', '🧪 Same-Score Lab', '📚 Source Material'])

history = db.attempts(demo_id)
diagnostics = en.diagnostic(history)
known_topics = list(dict.fromkeys(x['topic'] for x in history))

if section == '🏠 Overview':
    st.subheader('A personalised preparation workbench')
    a, b, c = st.columns(3)
    a.metric('Questions attempted', len(history))
    b.metric('Overall accuracy', f"{100 * sum(x['correct'] for x in history) / len(history):.0f}%" if history else '—')
    c.metric('Tracked concepts', len(diagnostics))
    st.write('Generate original custom-topic questions with Gemini AI, take confidence-aware tests, track weak areas, and plan revision.')
    if not secret('GEMINI_API_KEY'):
        st.warning('To enable cloud AI, add GEMINI_API_KEY to Streamlit App settings → Secrets. The curated question bank still works without it.')
    else:
        st.success('Gemini API key configured. Cloud AI is available.')
    st.caption('Demo only: questions are AI-generated and may contain errors. Exam labels do not guarantee official exam-format alignment.')

elif section == '📚 Source Material':
    st.subheader('Your notes and learning resources')
    uploads = st.file_uploader('Upload PDF, DOCX, TXT or MD', type=['pdf', 'docx', 'txt', 'md'], accept_multiple_files=True)
    pasted = st.text_area('Or paste notes', height=160)
    if st.button('Extract material'):
        chunks = [pasted]
        for f in uploads or []:
            try:
                if f.name.lower().endswith('.pdf'):
                    from pypdf import PdfReader
                    chunks.append('\n'.join(p.extract_text() or '' for p in PdfReader(BytesIO(f.getvalue())).pages[:35]))
                elif f.name.lower().endswith('.docx'):
                    from docx import Document
                    chunks.append('\n'.join(p.text for p in Document(BytesIO(f.getvalue())).paragraphs))
                else:
                    chunks.append(f.getvalue().decode('utf-8', errors='replace'))
            except Exception as e:
                st.warning(f'Could not extract {f.name}: {e}')
        st.session_state.source_text = '\n'.join(chunks)[:60000]
        st.success(f"Extracted {len(st.session_state.source_text):,} characters for this session.")
    if st.session_state.source_text:
        with st.expander('Preview extracted text'):
            st.text(st.session_state.source_text[:4000])
        st.caption('Extracted notes can guide Gemini quiz generation in Diagnostic Test. Scanned PDFs need OCR.')
        if st.button('Create source recall flashcards'):
            snippets = en.extract_candidates(st.session_state.source_text)
            for s in snippets[:12]:
                db.card_add(demo_id, 'Uploaded material', 'Recall and explain this passage:', s)
            st.success(f'Added {min(len(snippets), 12)} cards.')

elif section == '📝 Diagnostic Test':
    st.subheader('Start a diagnostic assessment')
    subjects = sorted({x[0] for x in en.SEEDS})
    subject_choice = st.selectbox('Subject', subjects + ['Custom subject'], index=subjects.index('Physics'))
    subject = st.text_input('Enter subject') if subject_choice == 'Custom subject' else subject_choice
    suggested = sorted({x[1] for x in en.SEEDS if x[0] == subject})
    topic_choice = st.selectbox('Topic', ['Enter custom topic'] + suggested)
    topic = st.text_input('Your topic', placeholder='e.g. Laws of Motion, Macbeth Act 1') if topic_choice == 'Enter custom topic' else topic_choice
    difficulty = st.selectbox('Difficulty', en.DIFFICULTIES)
    count = st.selectbox('Number of questions', [5, 10, 15, 20])
    mode = st.radio('Question source', ['✨ Gemini AI (cloud)', '📘 Curated demo bank'], horizontal=True)
    if st.button('Generate assessment', type='primary'):
        st.session_state.quiz = []
        st.session_state.results = None
        st.session_state.references = []
        if not subject.strip() or not topic.strip():
            st.error('Enter both subject and topic.')
        elif mode.startswith('✨'):
            key = secret('GEMINI_API_KEY')
            if not key:
                st.error('Missing GEMINI_API_KEY. Add it under Streamlit → App settings → Secrets.')
            else:
                with st.spinner('Searching educational references and generating/reviewing questions with Gemini…'):
                    try:
                        quiz, refs = en.cloud_quiz(subject, topic, difficulty, count, exam, grade, api_key=key, model=secret('GEMINI_MODEL', 'gemini-2.5-flash'), source_text=st.session_state.source_text)
                        st.session_state.quiz = quiz
                        st.session_state.references = refs
                    except Exception as e:
                        st.error(str(e))
        else:
            bank = en.question_bank(subject, topic, difficulty)
            if not bank:
                st.warning('No curated questions for this exact combination. Try Gemini AI or a seeded topic.')
            else:
                st.session_state.quiz = en.safe_quiz(bank, count)
                if len(bank) < count:
                    st.info(f'Only {len(bank)} curated questions are available for this combination.')
        st.session_state.quiz_key = en.uuid_hash(str([q['id'] for q in st.session_state.quiz]) + str(__import__('time').time()))
    quiz = st.session_state.quiz
    if quiz:
        st.info(f'{len(quiz)} questions ready. Select an answer and confidence level for each.')
        with st.form('assessment_form'):
            answers, confidences = [], []
            for i, q in enumerate(quiz):
                st.markdown(f"**Q{i+1}. {q['question']}**")
                answers.append(st.radio('Choose one', ['— Select —'] + q['options'], key=f"answer_{st.session_state.quiz_key}_{i}", label_visibility='collapsed'))
                confidences.append(st.select_slider('Confidence', options=[1, 2, 3], value=2, key=f"confidence_{st.session_state.quiz_key}_{i}", format_func=lambda x: {1:'Low',2:'Medium',3:'High'}[x]))
                st.divider()
            submitted = st.form_submit_button('Submit and score', type='primary')
        if submitted:
            if '— Select —' in answers:
                st.error('Please answer every question before submitting.')
            else:
                rows = en.score_quiz(quiz, answers, confidences)
                db.save_attempt(demo_id, rows)
                st.session_state.results = rows
        if st.session_state.results:
            rows = st.session_state.results
            st.success(f"Score: {sum(r['correct'] for r in rows)}/{len(rows)}")
            for i, r in enumerate(rows):
                with st.expander(f"Q{i+1}: {'✅ Correct' if r['correct'] else '❌ Incorrect'} — {r['question'][:90]}"):
                    st.write('Your answer:', r['selected'])
                    st.write('Correct answer:', r['answer'])
                    st.write('Explanation:', r['explanation'])
                    if r.get('source_url'):
                        st.markdown(f"[Supporting reference]({r['source_url']})")

elif section == '📊 My Diagnostics':
    st.subheader('Confidence-aware diagnostics')
    if diagnostics:
        df = pd.DataFrame(diagnostics)
        st.dataframe(df, use_container_width=True, hide_index=True)
        fig = px.scatter(df, x='confidence', y='accuracy', size='attempted', color='zone', hover_name='topic', range_x=[0, 100], range_y=[0, 100], title='Accuracy vs confidence')
        fig.add_hline(y=70, line_dash='dash')
        fig.add_vline(x=67, line_dash='dash')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info('Complete a diagnostic test to see your learning profile.')

elif section == '🗓️ Study Planner':
    st.subheader('Personalised study planner')
    topics_text = st.text_area('Topics (one per line)', value='\n'.join(x['topic'] for x in diagnostics) if diagnostics else '')
    days = st.slider('Days', 3, 30, 7)
    minutes = st.slider('Minutes per day', 15, 180, 60, step=15)
    if st.button('Create study plan'):
        topics = [x.strip() for x in topics_text.splitlines() if x.strip()]
        st.dataframe(pd.DataFrame(en.schedule(topics, days, minutes, exam)), use_container_width=True, hide_index=True)

elif section == '🃏 Flashcards':
    st.subheader('Flashcards')
    with st.form('add_card'):
        topic = st.text_input('Topic')
        front = st.text_area('Question / front')
        back = st.text_area('Answer / back')
        if st.form_submit_button('Add flashcard'):
            if topic and front and back:
                db.card_add(demo_id, topic, front, back)
                st.success('Flashcard saved.')
            else:
                st.warning('Fill in all fields.')
    cards = db.card_get(demo_id)
    for card_id, topic, front, back, due, interval in cards:
        with st.expander(f'{topic} — {front[:75]}'):
            st.write(front)
            st.write('**Answer:**', back)
            st.caption(f'Next review: {due}')
            a, b = st.columns(2)
            if a.button('Remembered', key='yes'+card_id):
                db.card_review(card_id, True)
                st.rerun()
            if b.button('Review again', key='no'+card_id):
                db.card_review(card_id, False)
                st.rerun()

elif section == '✅ Revision Tracker':
    st.subheader('Revision tracker')
    topic = st.text_input('Topic to track')
    status = st.selectbox('Status', ['Not started', 'In progress', 'Revised', 'Mastered'])
    if st.button('Save revision status') and topic.strip():
        db.revision_set(demo_id, topic.strip(), status)
        st.success('Updated.')
    st.dataframe(pd.DataFrame(db.revision_get(demo_id), columns=['Topic', 'Status', 'Updated']), use_container_width=True, hide_index=True)

elif section == '🎞️ Learning Reels':
    st.subheader('Learning micro-reels')
    st.caption('Short, swipe-friendly study prompts from the curated question bank.')
    bank = en.question_bank()
    for q in en.safe_quiz(bank, 5):
        with st.expander(f"{q['topic']} · {q['question']}"):
            st.write('**Answer:**', q['answer'])
            st.write(q['explanation'])

elif section == '💬 Concept Coach':
    st.subheader('Gemini concept coach')
    st.caption('Ask for a concept explanation, worked example or study tip.')
    topic = st.text_input('What would you like explained?')
    if st.button('Explain with Gemini'):
        key = secret('GEMINI_API_KEY')
        if not key:
            st.error('Configure GEMINI_API_KEY in Streamlit Secrets first.')
        elif not topic.strip():
            st.warning('Enter a concept or question.')
        else:
            with st.spinner('Thinking…'):
                try:
                    data = en._gemini_json('Explain this educational concept clearly and accurately for '+grade+' studying '+exam+'. Return JSON with keys "explanation" (string), "example" (string), and "quick_check" (string). Topic: '+topic[:1500], key, secret('GEMINI_MODEL', 'gemini-2.5-flash'))
                    st.write(data.get('explanation', ''))
                    st.markdown('**Worked example**')
                    st.write(data.get('example', ''))
                    st.markdown('**Quick check**')
                    st.write(data.get('quick_check', ''))
                except Exception as e:
                    st.error(str(e))

elif section == '🧪 Same-Score Lab':
    st.subheader('Same score, different learning profiles')
    st.write('Two learners can get the same number of answers correct but have very different confidence patterns.')
    demo_a = en.quadrant(.6, .9)
    demo_b = en.quadrant(.6, .3)
    c1, c2 = st.columns(2)
    c1.metric('Learner A', '60% accuracy')
    c1.write('90% confidence → **'+demo_a[0]+'**')
    c1.write(demo_a[1])
    c2.metric('Learner B', '60% accuracy')
    c2.write('30% confidence → **'+demo_b[0]+'**')
    c2.write(demo_b[1])

st.divider()
st.caption('Educational demonstration. Use fictional identifiers; this SQLite-backed app has no authentication and storage may reset on redeployment.')
