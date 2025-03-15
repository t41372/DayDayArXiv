import Image from "next/image"

export function Sidebar() {
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg p-4 shadow-sm border border-black border-opacity-50">
        <h3 className="text-xl font-medium mb-4">关于</h3>
        <div className="flex items-center mb-4">
          <a href="https://github.com/t41372">
            <img
              src="https://simpleicons.org/icons/github.svg"
              alt="GitHub"
              className="h-6 w-6 mr-2"
            />
          </a>
        </div>
        <p className="text-sm text-[#45454a]">
          这是一个 arXiv 快讯网站，提供arXiv 每日论文的介绍和总结。目标是让你像刷信息流一样，轻松的跟上最新的 arXiv 论文。<br /> <br />
          摘要与 TLDR 由 AI 自动生成，可能不准确，欢迎反馈。<br /><br />
          目前仅支持 cs.AI 领域的论文，需要其他领域跟我说一声。<br /><br />
          每日 UTC 00:20 更新。
        </p>
      </div>
    </div>
  )
}

