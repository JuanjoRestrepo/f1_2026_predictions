import ReactMarkdown from "react-markdown";

interface RaceReportProps {
  markdownContent: string;
}

export function RaceReport({ markdownContent }: RaceReportProps) {
  return (
    <div className="w-full">
      <div className="prose prose-invert prose-sm md:prose-base max-w-none text-gray-300">
        <ReactMarkdown
          components={{
            h1: ({node, ...props}) => <h1 className="text-white text-2xl md:text-3xl font-bold mb-4" {...props} />,
            h2: ({node, ...props}) => <h2 className="text-white text-xl md:text-2xl font-bold mt-6 mb-3" {...props} />,
            h3: ({node, ...props}) => <h3 className="text-white text-lg font-semibold mt-4 mb-2" {...props} />,
            p: ({node, ...props}) => <p className="mb-4 leading-relaxed" {...props} />,
            strong: ({node, ...props}) => <strong className="text-white font-semibold" {...props} />,
            ul: ({node, ...props}) => <ul className="list-disc pl-5 mb-4" {...props} />,
            li: ({node, ...props}) => <li className="mb-1" {...props} />,
          }}
        >
          {markdownContent}
        </ReactMarkdown>
      </div>
    </div>
  );
}
