import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

interface RaceReportProps {
  markdownContent: string;
}

export function RaceReport({ markdownContent }: RaceReportProps) {
  return (
    <div className="w-full">
      <div className="prose prose-invert prose-sm md:prose-base max-w-none text-gray-300">
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[rehypeKatex]}
          components={{
            h1: ({ node, ...props }) => (
              <h1
                className="text-white text-2xl md:text-3xl font-bold mb-4"
                {...props}
              />
            ),
            h2: ({ node, ...props }) => (
              <h2
                className="text-white text-xl md:text-2xl font-bold mt-6 mb-3"
                {...props}
              />
            ),
            h3: ({ node, ...props }) => (
              <h3
                className="text-white text-lg font-semibold mt-4 mb-2"
                {...props}
              />
            ),
            p: ({ node, ...props }) => (
              <p className="mb-4 leading-relaxed" {...props} />
            ),
            strong: ({ node, ...props }) => (
              <strong className="text-white font-semibold" {...props} />
            ),
            ul: ({ node, ...props }) => (
              <ul className="list-disc pl-5 mb-4" {...props} />
            ),
            li: ({ node, ...props }) => <li className="mb-1" {...props} />,
            // ── Table support (remark-gfm) ──────────────────────────────────
            table: ({ node, ...props }) => (
              <div className="overflow-x-auto my-6 rounded-lg border border-white/10">
                <table
                  className="w-full text-xs md:text-sm text-left border-collapse"
                  {...props}
                />
              </div>
            ),
            thead: ({ node, ...props }) => (
              <thead
                className="bg-white/5 text-gray-400 uppercase tracking-widest text-[10px] md:text-xs"
                {...props}
              />
            ),
            tbody: ({ node, ...props }) => (
              <tbody className="divide-y divide-white/5" {...props} />
            ),
            tr: ({ node, ...props }) => (
              <tr
                className="hover:bg-white/5 transition-colors"
                {...props}
              />
            ),
            th: ({ node, ...props }) => (
              <th
                className="px-3 py-2 font-semibold text-gray-300 border-b border-white/10"
                {...props}
              />
            ),
            td: ({ node, ...props }) => (
              <td className="px-3 py-2 text-gray-400" {...props} />
            ),
            // ── Code blocks ─────────────────────────────────────────────────
            code: ({ node, className, children, ...props }) => {
              // Check if inline
              const contentStr = String(children);
              const isInline = !contentStr.includes("\n");
              if (!isInline) {
                return (
                  <code className="text-gray-300 font-mono block" {...props}>
                    {children}
                  </code>
                );
              }
              // Inline code
              return (
                <code
                  className="bg-white/10 text-red-300 rounded px-1 py-0.5 text-xs md:text-sm font-mono"
                  {...props}
                >
                  {children}
                </code>
              );
            },
            pre: ({ node, ...props }) => (
              <pre
                className="bg-black/40 border border-white/10 rounded-lg p-4 my-4 overflow-x-auto text-xs md:text-sm font-mono text-gray-300 whitespace-pre-wrap"
                {...props}
              />
            ),
            // ── Horizontal rule ─────────────────────────────────────────────
            hr: ({ node, ...props }) => (
              <hr className="border-white/10 my-6" {...props} />
            ),
            // ── Blockquote ──────────────────────────────────────────────────
            blockquote: ({ node, ...props }) => (
              <blockquote
                className="border-l-2 border-f1red pl-4 italic text-gray-400 my-4"
                {...props}
              />
            ),
          }}
        >
          {markdownContent}
        </ReactMarkdown>
      </div>
    </div>
  );
}
