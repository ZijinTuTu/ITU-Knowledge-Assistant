'use client';

import { useEffect, useMemo, useState } from 'react';

type UILanguage = 'en' | 'zh' | 'ja';
type ThemeMode = 'system' | 'light' | 'dark';
type AnswerLanguage = 'en' | 'zh' | 'ja';

type Citation = {
  source_id: number;
  title: string;
  filename: string;
  page_start?: number;
  page_end?: number;
  score: number;
  label?: string;
};

type AskResponse = {
  query: string;
  answer: string;
  citations: Citation[];
  results: Array<{
    chunk_id?: string;
    filename: string;
    title: string;
    source_org?: string;
    doc_type?: string;
    year?: number;
    language?: string;
    page_start?: number;
    page_end?: number;
    chunk_chars?: number;
    text: string;
    score: number;
    raw_score?: number;
  }>;
};

const translations = {
  en: {
    title: 'ITU Assistant',
    subtitle: 'Search and ask questions across your ITU knowledge base.',
    ask: 'Ask',
    querying: 'Thinking...',
    queryPlaceholder:
      'Ask a question about ITU reports, statistics, strategy, or digital divide…',
    uiLanguage: 'UI Language',
    answerLanguage: 'Answer Language',
    theme: 'Theme',
    system: 'System',
    light: 'Light',
    dark: 'Dark',
    english: 'English',
    chinese: 'Chinese',
    japanese: 'Japanese',
    answer: 'Answer',
    sources: 'Sources',
    empty: 'Your answer will appear here.',
    error: 'Something went wrong. Please check whether the API is running.',
    tips: 'Suggested questions',
    q1: 'What does the report say about the digital divide?',
    q2: 'How many people are using the Internet globally?',
    q3: 'What barriers to digital uptake are mentioned?',
    api: 'API Base URL',
    footer:
      'Designed for multilingual ITU knowledge retrieval and grounded answers.',
    loading: 'Loading interface...',
  },
  zh: {
    title: 'ITU Assistant',
    subtitle: '基于你的 ITU 知识库进行检索与问答。',
    ask: '提问',
    querying: '思考中...',
    queryPlaceholder:
      '输入一个关于 ITU 报告、统计、战略或数字鸿沟的问题……',
    uiLanguage: '界面语言',
    answerLanguage: '回答语言',
    theme: '主题',
    system: '跟随系统',
    light: '浅色',
    dark: '深色',
    english: '英语',
    chinese: '中文',
    japanese: '日语',
    answer: '回答',
    sources: '来源',
    empty: '回答会显示在这里。',
    error: '请求失败，请检查后端 API 是否正常运行。',
    tips: '推荐问题',
    q1: '报告对数字鸿沟是怎么说的？',
    q2: '全球有多少人在使用互联网？',
    q3: '报告提到了哪些数字接入障碍？',
    api: 'API 地址',
    footer: '适用于多语言 ITU 知识检索与基于证据的回答。',
    loading: '正在加载界面...',
  },
  ja: {
    title: 'ITU Assistant',
    subtitle: 'ITU ナレッジベースを対象に検索と質問応答を行います。',
    ask: '質問する',
    querying: '考えています...',
    queryPlaceholder:
      'ITU のレポート、統計、戦略、デジタル格差について質問してください…',
    uiLanguage: 'UI 言語',
    answerLanguage: '回答言語',
    theme: 'テーマ',
    system: 'システム',
    light: 'ライト',
    dark: 'ダーク',
    english: '英語',
    chinese: '中国語',
    japanese: '日本語',
    answer: '回答',
    sources: '出典',
    empty: 'ここに回答が表示されます。',
    error: '問題が発生しました。API が起動しているか確認してください。',
    tips: '質問例',
    q1: 'レポートはデジタル格差について何と言っていますか？',
    q2: '世界で何人がインターネットを使っていますか？',
    q3: 'デジタル利用を妨げる要因として何が挙げられていますか？',
    api: 'API ベース URL',
    footer: '多言語の ITU ナレッジ検索と根拠付き回答のための画面です。',
    loading: 'インターフェースを読み込み中...',
  },
} as const;

export default function Page() {
  const [mounted, setMounted] = useState(false);

  const [uiLanguage, setUiLanguage] = useState<UILanguage>('en');
  const [answerLanguage, setAnswerLanguage] = useState<AnswerLanguage>('en');
  const [theme, setTheme] = useState<ThemeMode>('system');
  const [apiBase, setApiBase] = useState(
    process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000'
  );
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState<Citation[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;

    const savedUiLanguage = localStorage.getItem('itu-ui-language') as
      | UILanguage
      | null;
    const savedAnswerLanguage = localStorage.getItem(
      'itu-answer-language'
    ) as AnswerLanguage | null;
    const savedTheme = localStorage.getItem('itu-theme') as ThemeMode | null;
    const savedApiBase = localStorage.getItem('itu-api-base');

    if (savedUiLanguage) setUiLanguage(savedUiLanguage);
    if (savedAnswerLanguage) setAnswerLanguage(savedAnswerLanguage);
    if (savedTheme) setTheme(savedTheme);
    if (savedApiBase) setApiBase(savedApiBase);
  }, [mounted]);

  useEffect(() => {
    if (!mounted) return;
    localStorage.setItem('itu-ui-language', uiLanguage);
  }, [uiLanguage, mounted]);

  useEffect(() => {
    if (!mounted) return;
    localStorage.setItem('itu-answer-language', answerLanguage);
  }, [answerLanguage, mounted]);

  useEffect(() => {
    if (!mounted) return;
    localStorage.setItem('itu-theme', theme);
  }, [theme, mounted]);

  useEffect(() => {
    if (!mounted) return;
    localStorage.setItem('itu-api-base', apiBase);
  }, [apiBase, mounted]);

  const t = translations[uiLanguage];

  const resolvedTheme = useMemo(() => {
    if (!mounted) return 'light';
    if (theme !== 'system') return theme;
    return window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light';
  }, [theme, mounted]);

  const isDark = resolvedTheme === 'dark';

  const answerLanguageName = {
    en: 'English',
    zh: 'Chinese',
    ja: 'Japanese',
  }[answerLanguage];

  const suggestedQuestions = [t.q1, t.q2, t.q3];

  async function handleAsk() {
    if (!query.trim()) return;

    setLoading(true);
    setError('');
    setAnswer('');
    setCitations([]);

    try {
      const finalQuery = `${query.trim()}\n\nPlease answer in ${answerLanguageName}.`;

      const response = await fetch(`${apiBase}/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: finalQuery,
          top_k: 4,
          fetch_k: 30,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data: AskResponse = await response.json();
      setAnswer(data.answer || '');
      setCitations(data.citations || []);
    } catch {
      setError(t.error);
    } finally {
      setLoading(false);
    }
  }

  function applySuggestion(text: string) {
    setQuery(text);
  }

  if (!mounted) {
    return (
      <div className="min-h-screen bg-neutral-50 text-neutral-900">
        <div className="mx-auto max-w-7xl px-4 py-8 md:px-6 lg:px-8">
          <div className="rounded-3xl border border-neutral-200 bg-white p-6 shadow-xl">
            <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
              ITU Assistant
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-neutral-500 md:text-base">
              Loading interface...
            </p>
          </div>
        </div>
      </div>
    );
  }

  const containerClass = isDark
    ? 'min-h-screen bg-neutral-950 text-neutral-100'
    : 'min-h-screen bg-neutral-50 text-neutral-900';

  const panelClass = isDark
    ? 'rounded-3xl border border-neutral-800 bg-neutral-900 shadow-xl'
    : 'rounded-3xl border border-neutral-200 bg-white shadow-xl';

  const inputClass = isDark
    ? 'w-full rounded-2xl border border-neutral-700 bg-neutral-950 px-4 py-3 text-sm text-neutral-100 outline-none focus:border-neutral-500'
    : 'w-full rounded-2xl border border-neutral-300 bg-white px-4 py-3 text-sm text-neutral-900 outline-none focus:border-neutral-500';

  const smallInputClass = isDark
    ? 'w-full rounded-xl border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none'
    : 'w-full rounded-xl border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 outline-none';

  const mutedClass = isDark ? 'text-neutral-400' : 'text-neutral-500';

  const buttonClass = isDark
    ? 'rounded-2xl bg-white px-5 py-3 text-sm font-medium text-neutral-900 transition hover:opacity-90 disabled:opacity-50'
    : 'rounded-2xl bg-neutral-900 px-5 py-3 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50';

  const suggestionClass = isDark
    ? 'rounded-2xl border border-neutral-700 bg-neutral-950 px-4 py-3 text-left text-sm hover:border-neutral-500'
    : 'rounded-2xl border border-neutral-200 bg-white px-4 py-3 text-left text-sm hover:border-neutral-400';

  return (
    <div className={containerClass} suppressHydrationWarning>
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-8 md:px-6 lg:px-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
              {t.title}
            </h1>
            <p className={`mt-2 max-w-2xl text-sm md:text-base ${mutedClass}`}>
              {t.subtitle}
            </p>
          </div>

          <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2 lg:w-auto lg:grid-cols-4">
            <div>
              <label className={`mb-1 block text-xs ${mutedClass}`}>
                {t.uiLanguage}
              </label>
              <select
                className={smallInputClass}
                value={uiLanguage}
                onChange={(e) => setUiLanguage(e.target.value as UILanguage)}
              >
                <option value="en">{translations[uiLanguage].english}</option>
                <option value="zh">{translations[uiLanguage].chinese}</option>
                <option value="ja">{translations[uiLanguage].japanese}</option>
              </select>
            </div>

            <div>
              <label className={`mb-1 block text-xs ${mutedClass}`}>
                {t.answerLanguage}
              </label>
              <select
                className={smallInputClass}
                value={answerLanguage}
                onChange={(e) =>
                  setAnswerLanguage(e.target.value as AnswerLanguage)
                }
              >
                <option value="en">{translations[uiLanguage].english}</option>
                <option value="zh">{translations[uiLanguage].chinese}</option>
                <option value="ja">{translations[uiLanguage].japanese}</option>
              </select>
            </div>

            <div>
              <label className={`mb-1 block text-xs ${mutedClass}`}>
                {t.theme}
              </label>
              <select
                className={smallInputClass}
                value={theme}
                onChange={(e) => setTheme(e.target.value as ThemeMode)}
              >
                <option value="system">{t.system}</option>
                <option value="light">{t.light}</option>
                <option value="dark">{t.dark}</option>
              </select>
            </div>

            <div className="sm:col-span-2 lg:col-span-1 lg:min-w-72">
              <label className={`mb-1 block text-xs ${mutedClass}`}>
                {t.api}
              </label>
              <input
                className={smallInputClass}
                value={apiBase}
                onChange={(e) => setApiBase(e.target.value)}
              />
            </div>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <div className={`${panelClass} p-5 md:p-6`}>
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t.queryPlaceholder}
                className={`${inputClass} min-h-40 resize-y`}
              />
              <div className="mt-4 flex justify-end">
                <button
                  className={buttonClass}
                  disabled={loading || !query.trim()}
                  onClick={handleAsk}
                >
                  {loading ? t.querying : t.ask}
                </button>
              </div>
            </div>

            <div className={`${panelClass} mt-6 p-5 md:p-6`}>
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-xl font-semibold">{t.answer}</h2>
              </div>

              {error ? (
                <div className="rounded-2xl border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              ) : answer ? (
                <div className="space-y-4">
                  <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-7">
                    {answer}
                  </pre>
                </div>
              ) : (
                <p className={`text-sm ${mutedClass}`}>{t.empty}</p>
              )}
            </div>
          </div>

          <div className="lg:col-span-5">
            <div className={`${panelClass} p-5 md:p-6`}>
              <h2 className="text-xl font-semibold">{t.sources}</h2>
              <div className="mt-4 space-y-3">
                {citations.length === 0 ? (
                  <p className={`text-sm ${mutedClass}`}>—</p>
                ) : (
                  citations.map((c, idx) => (
                    <div
                      key={`${c.filename}-${c.page_start}-${idx}`}
                      className={
                        isDark
                          ? 'rounded-2xl border border-neutral-800 bg-neutral-950 p-4'
                          : 'rounded-2xl border border-neutral-200 bg-neutral-50 p-4'
                      }
                    >
                      <div className="text-sm font-medium">{c.filename}</div>
                      <div className={`mt-1 text-xs ${mutedClass}`}>
                        {c.title || 'Untitled'}
                      </div>
                      <div className={`mt-2 text-xs ${mutedClass}`}>
                        Pages {c.page_start}-{c.page_end} · score{' '}
                        {Number(c.score || 0).toFixed(4)}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className={`${panelClass} mt-6 p-5 md:p-6`}>
              <h2 className="text-xl font-semibold">{t.tips}</h2>
              <div className="mt-4 grid gap-3">
                {suggestedQuestions.map((item) => (
                  <button
                    key={item}
                    className={suggestionClass}
                    onClick={() => applySuggestion(item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className={`text-center text-xs ${mutedClass}`}>{t.footer}</div>
      </div>
    </div>
  );
}
