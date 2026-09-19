#!/usr/bin/env python3
"""
评分索引表页码定位脚本。
用法：先用占位页码生成 docx -> 转 PDF -> 本脚本按"锚点字符串"定位各评分项所在页码 -> 回填 pages.js -> 重新生成。
由于索引表行数固定，回填真实页码后分页不变，定位结果保持有效。

调用：python3 page_locator.py <pdf文件> <anchors.json>
anchors.json 形如: {"price":"壹佰贰拾玖万...", "tech":"详细建设技术参数清单...", ...}
输出：found.json （键->页码，页码=PDF物理页=页脚页码）
"""
import sys, json, subprocess, os

def norm(s):  # 去除所有空白，规避 pdftotext 在汉字间插入空格/换行
    return ''.join(s.split())

def main():
    pdf, anchors_file = sys.argv[1], sys.argv[2]
    txt = pdf + '.txt'
    subprocess.run(['pdftotext', pdf, txt], check=True)
    pages = open(txt, encoding='utf-8').read().split('\f')
    P = [norm(p) for p in pages]
    anchors = json.load(open(anchors_file, encoding='utf-8'))
    res = {}
    for k, a in anchors.items():
        na = norm(a)
        res[k] = next((i + 1 for i, t in enumerate(P) if na in t), None)
    print('total pages:', len(pages))
    for k in anchors:
        print(k, '->', res[k])
    json.dump(res, open('found.json', 'w'), ensure_ascii=False)

if __name__ == '__main__':
    main()
