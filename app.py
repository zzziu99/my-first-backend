import sqlite3
import os
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)
DATABASE = os.path.join(os.path.dirname(__file__), 'database.db')

# Ordered list of categories for the nav
CATEGORIES = ["图书馆", "食堂", "宿舍", "校园服务", "选课", "考试", "毕业要求", "奖学金", "德育积分", "综合素质实践", "社团", "其他"]


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def get_tables():
    conn = get_db()
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence' ORDER BY name"
    ).fetchall()
    conn.close()
    return [r['name'] for r in rows]


@app.route('/')
def index():
    return render_template('index.html')


# Return list of categories (ordered) for frontend nav
@app.route('/api/categories')
def list_categories():
    existing = get_tables()
    ordered = [c for c in CATEGORIES if c in existing]
    return jsonify(ordered)


# GET /api/qa?category=xxx — fetch Q&A for a single category
@app.route('/api/qa')
def get_qa():
    category = request.args.get('category', '')
    if not category:
        return jsonify({'error': 'missing category'}), 400
    conn = get_db()
    rows = conn.execute(f'SELECT * FROM "{category}"').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# Chat search — multi-keyword scoring across ALL tables
@app.route('/api/handbook', methods=['POST'])
def search_all():
    data = request.get_json() or {}
    question = data.get('question', '').strip()
    if not question:
        return jsonify({'answer': '请输入问题。'})

    conn = get_db()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
    ).fetchall()

    # Split question into meaningful keywords
    import re
    parts = re.split(r'[，。？\s,\.\?!、：:；;()（）【】\[\]「」{}]', question)
    keywords = [p for p in parts if len(p) >= 1 and p.strip()]

    # Characters to ignore (common stop-words in Chinese)
    stop_chars = {'的', '了', '是', '在', '有', '和', '就', '不', '也', '都', '而', '之',
                  '吗', '呢', '吧', '啊', '呀', '么', '我', '你', '他', '它',
                  '这', '那', '哪', '什', '怎', '谁', '几', '多', '很', '太',
                  '能', '会', '要', '去', '到', '上', '下', '大', '小', '个',
                  '为', '与', '及', '或', '做', '对', '被', '把', '让', '给'}
    chars = [c for c in question if '一' <= c <= '鿿' and c not in stop_chars]

    results = []
    for t in tables:
        name = t['name']
        try:
            rows = conn.execute(f'SELECT question, answer FROM "{name}"').fetchall()
            for row in rows:
                q_text, a_text = row['question'], row['answer']
                score = 0
                matched_kws = set()

                # Priority 1: question partially contains user's input, or vice versa
                if question in q_text or q_text in question:
                    score += 100
                    matched_kws.add('exact_q')
                if question in a_text:
                    score += 80
                    matched_kws.add('exact_a')

                # Priority 2: keyword matches
                for kw in keywords:
                    if len(kw) < 2:
                        continue
                    if kw in q_text:
                        score += 15
                        matched_kws.add(kw)
                    elif kw in a_text:
                        score += 8
                        matched_kws.add(kw)

                # Priority 3: character-level closeness
                for c in chars:
                    if c in q_text:
                        score += 2
                    elif c in a_text:
                        score += 1

                if score > 0:
                    results.append({
                        'question': q_text,
                        'answer': a_text,
                        'category': name,
                        'score': score,
                        'hits': len(matched_kws)
                    })
        except sqlite3.OperationalError:
            pass

    conn.close()

    if results:
        # Sort: highest score first, then most keyword hits, then shortest question
        results.sort(key=lambda r: (-r['score'], -r['hits'], len(r['question'])))
        best = results[0]
        return jsonify({
            'answer': best['answer'],
            'category': best['category'],
            'related': best['question']
        })

    return jsonify({'answer': '抱歉，知识库中没有找到相关答案，请咨询辅导员或教务处。'})


@app.route('/api/stats')
def get_stats():
    conn = get_db()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
    ).fetchall()

    total_categories = len(tables)
    total_qa = 0
    for t in tables:
        row = conn.execute(f'SELECT COUNT(*) as cnt FROM "{t["name"]}"').fetchone()
        total_qa += row['cnt']

    conn.close()
    return jsonify({
        'categories': total_categories,
        'total_qa': total_qa,
        'avg_per_category': round(total_qa / total_categories) if total_categories > 0 else 0
    })


if __name__ == '__main__':
    app.run(debug=True, port=5000)
