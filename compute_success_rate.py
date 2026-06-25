#!/usr/bin/env python3
"""Compute success rate from eval_qwen_webarena_json render HTMLs and configs."""

import json
import os
import re
import ast
import html as html_mod
from collections import Counter
from urllib.parse import urlparse, parse_qs

EXTRACT_DIR = '/tmp/eval_qwen_webarena_json/eval_qwen_webarena_json'
RENDER_DIR = EXTRACT_DIR
TRACES_DIR = os.path.join(EXTRACT_DIR, 'traces')
ERROR_FILE = os.path.join(EXTRACT_DIR, 'error.txt')
TEST_RAW = 'webarena-main/config_files/test.raw.json'


def load_task_map():
    with open(TEST_RAW) as f:
        data = json.load(f)
    return {t['task_id']: t for t in data}


def get_render_task_ids():
    ids = []
    for f in os.listdir(RENDER_DIR):
        m = re.match(r'render_(\d+)\.html', f)
        if m:
            ids.append(int(m.group(1)))
    return sorted(ids)


def get_error_task_ids():
    ids = []
    if os.path.exists(ERROR_FILE):
        with open(ERROR_FILE) as f:
            for line in f:
                m = re.search(r'/(\d+)\.json', line)
                if m:
                    ids.append(int(m.group(1)))
    return sorted(set(ids))


def extract_last_answer_from_html(html_path):
    """Extract the answer from the last action in render HTML."""
    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    pre_blocks = re.findall(r"<pre>(.*?)</pre>", content, re.DOTALL)
    answers = []
    for pre in pre_blocks:
        pre_clean = html_mod.unescape(pre)
        if "'action_type'" not in pre_clean:
            continue
        ans_m = re.search(r"'answer':\s*'([^']*)'", pre_clean)
        answers.append(ans_m.group(1) if ans_m else "")
    return answers[-1] if answers else ""


def extract_last_url_from_html(html_path):
    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    urls = re.findall(r"<h3 class='url'><a href=([^>]+)>URL:", content)
    if urls:
        return html_mod.unescape(urls[-1].strip())
    return None


def extract_eval_from_html(html_path):
    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    body_match = re.search(r'<body>\s*<pre>(.*?)</pre>', content, re.DOTALL)
    if not body_match:
        return None
    config_text = html_mod.unescape(body_match.group(1))
    eval_match = re.search(r"eval:\s*(\{.*)$", config_text, re.DOTALL)
    if not eval_match:
        return None
    eval_str = eval_match.group(1).strip()
    try:
        return ast.literal_eval(eval_str)
    except Exception:
        return None


def clean_answer(answer):
    answer = answer.strip()
    if (answer.startswith("'") and answer.endswith("'")) or \
       (answer.startswith('"') and answer.endswith('"')):
        answer = answer[1:-1]
    return answer.lower()


def exact_match(ref, pred):
    return clean_answer(ref) == clean_answer(pred)


def must_include(ref, pred):
    return clean_answer(ref) in clean_answer(pred)


def evaluate_string_match(ref_answers, answer):
    """Evaluate string_match tasks following WebArena logic."""
    if not ref_answers:
        return 0.0

    score = 1.0
    for approach, value in ref_answers.items():
        if approach == 'exact_match':
            score *= float(exact_match(value, answer))

        elif approach == 'must_include':
            if isinstance(value, list):
                for v in value:
                    # WebArena uses tokenize=True when len(value)==1
                    # to prevent false positives like "0" matching in "30"
                    tokenize = len(value) == 1
                    if tokenize and len(clean_answer(v)) == 1:
                        # Simple word-boundary tokenization
                        tokens = re.findall(r'\b\w+\b', clean_answer(answer))
                        score *= float(clean_answer(v) in tokens)
                    else:
                        score *= float(must_include(v, answer))
            else:
                score *= float(must_include(value, answer))

        elif approach == 'fuzzy_match':
            if value == 'N/A':
                score *= float(exact_match('N/A', answer))
            elif isinstance(value, list):
                pred_clean = clean_answer(answer)
                matches = sum(1 for ref in value if clean_answer(ref) in pred_clean)
                score *= float(matches >= max(1, len(value) * 0.5))
            else:
                score *= float(exact_match(value, answer))
    return score


def evaluate_url_match(ref_url, last_url):
    if not ref_url or not last_url:
        return 0.0

    def clean_url(url):
        return str(url).rstrip('/')

    def parse_url(url):
        parsed = urlparse(url)
        base = parsed.netloc + parsed.path
        query = parse_qs(parsed.query)
        return base, query

    ref_base, ref_query = parse_url(ref_url)
    last_base, last_query = parse_url(last_url)

    if ref_base != last_base:
        return 0.0
    for k, v in ref_query.items():
        if k not in last_query:
            return 0.0
        if sorted(v) != sorted(last_query[k]):
            return 0.0
    return 1.0


def main():
    task_map = load_task_map()
    render_ids = get_render_task_ids()
    error_ids = get_error_task_ids()

    print(f"{'='*60}")
    print(f"  EVALUATION — eval_qwen_webarena_json")
    print(f"{'='*60}")
    print(f"  Render HTMLs:  {len(render_ids)} tasks")
    print(f"  Traces:        {len(os.listdir(TRACES_DIR)) if os.path.exists(TRACES_DIR) else 0} zip files")
    print(f"  Errors:        {len(error_ids)} tasks (IDs: {error_ids})")
    print()

    results = []
    eval_type_counts = Counter()

    for tid in sorted(render_ids):
        task_config_raw = task_map.get(tid)
        if not task_config_raw:
            print(f"  WARNING: Task {tid} not found")
            continue

        html_path = os.path.join(RENDER_DIR, f'render_{tid}.html')
        if not os.path.exists(html_path):
            continue

        html_eval = extract_eval_from_html(html_path)
        eval_config = html_eval if html_eval else task_config_raw.get('eval', {})
        eval_types = eval_config.get('eval_types', [])

        if tid in error_ids:
            results.append((tid, 'error', 0.0, 'crash'))
            eval_type_counts['error'] += 1
            continue

        answer = extract_last_answer_from_html(html_path)
        score = 0.0
        eval_method = 'unknown'

        if 'string_match' in eval_types:
            eval_method = 'string_match'
            ref_answers = eval_config.get('reference_answers', {})
            score = evaluate_string_match(ref_answers, answer)

        elif 'url_match' in eval_types:
            eval_method = 'url_match'
            last_url = extract_last_url_from_html(html_path)
            ref_url = eval_config.get('reference_url', '')
            if last_url and ref_url:
                score = evaluate_url_match(ref_url, last_url)

        elif 'program_html' in eval_types:
            eval_method = 'program_html'
            score = -1.0

        eval_type_counts[eval_method] += 1
        results.append((tid, eval_method, score, answer[:80] if answer else '(empty)'))

    # Print detailed
    print(f"{'Task':<6} {'Type':<15} {'Score':<8} {'Result':<8} {'Answer'}")
    print("-" * 90)

    pass_count = fail_count = error_count = unknown_count = 0
    pass_tasks = []
    fail_tasks = []

    for tid, method, score, ans in results:
        if score == 1.0:
            status, pass_count = 'PASS', pass_count + 1
            pass_tasks.append(tid)
        elif score == 0.0:
            if method == 'error':
                status, error_count = 'ERROR', error_count + 1
            else:
                status, fail_count = 'FAIL', fail_count + 1
                fail_tasks.append(tid)
        else:
            status, unknown_count = 'UNKNOWN', unknown_count + 1
        print(f"{tid:<6} {method:<15} {score:<8} {status:<8} {ans[:60]}")

    print("-" * 90)
    total = len(results)
    evaluated = pass_count + fail_count

    print(f"\n{'='*60}")
    print(f"  RESULTS")
    print(f"{'='*60}")
    print(f"  Total attempted:  {total}")
    print(f"  PASS:             {pass_count}")
    print(f"  FAIL:             {fail_count}")
    print(f"  ERROR (crash):    {error_count}")
    print(f"  UNKNOWN:          {unknown_count}")
    print(f"  ───────────────────────────")
    if evaluated > 0:
        print(f"  Success Rate:     {pass_count}/{evaluated} = {pass_count/evaluated*100:.1f}%")
    if total > 0:
        print(f"  Success (w/ err): {pass_count}/{total} = {pass_count/total*100:.1f}%")

    print(f"\n  Eval types:")
    for et, c in eval_type_counts.most_common():
        print(f"    {et}: {c}")

    # Common fail answers
    print(f"\n  Most common FAIL answers:")
    fail_answers = Counter()
    for tid, method, score, ans in results:
        if score == 0.0 and method != 'error':
            fail_answers[ans[:80]] += 1
    for ans, c in fail_answers.most_common(5):
        print(f"    [{c}x] {ans}")


if __name__ == '__main__':
    main()
