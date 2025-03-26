import Image from "next/image"
import { useEffect, useState } from "react"

// Background settings component
function BackgroundSettings() {
  const DEFAULT_COLOR = "#fffef7"
  const [color, setColor] = useState(DEFAULT_COLOR)
  const [imageUrl, setImageUrl] = useState("")

  useEffect(() => {
    // Load saved settings from localStorage
    const savedColor = localStorage.getItem("background-color")
    const savedImage = localStorage.getItem("background-image")
    if (savedColor) setColor(savedColor)
    if (savedImage) setImageUrl(savedImage)
  }, [])

  const handleColorChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newColor = e.target.value
    setColor(newColor)
    localStorage.setItem("background-color", newColor)
    document.body.style.backgroundColor = newColor
    if (!imageUrl) document.body.style.backgroundImage = "none"
  }

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      const reader = new FileReader()
      reader.onloadend = () => {
        const dataUrl = reader.result as string
        setImageUrl(dataUrl)
        localStorage.setItem("background-image", dataUrl)
        document.body.style.backgroundImage = `url(${dataUrl})`
        document.body.style.backgroundSize = "cover"
        document.body.style.backgroundPosition = "center"
        document.body.style.backgroundAttachment = "fixed"
      }
      reader.readAsDataURL(file)
    }
  }

  const clearBackground = () => {
    setImageUrl("")
    localStorage.removeItem("background-image")
    document.body.style.backgroundImage = "none"
    document.body.style.backgroundColor = color
  }

  const restoreDefaults = () => {
    setColor(DEFAULT_COLOR)
    setImageUrl("")
    localStorage.removeItem("background-image")
    localStorage.setItem("background-color", DEFAULT_COLOR)
    document.body.style.backgroundImage = "none"
    document.body.style.backgroundColor = DEFAULT_COLOR
  }

  return (
    <div className="bg-white/85 backdrop-blur-sm rounded-lg p-4 shadow-sm border border-black border-opacity-50">
      <h3 className="text-xl font-medium mb-4">背景设置</h3>
      <div className="space-y-4">
        <div>
          <label className="block text-sm text-[#45454a] mb-2">背景颜色</label>
          <input
            type="color"
            value={color}
            onChange={handleColorChange}
            className="w-full h-10 rounded cursor-pointer"
          />
        </div>
        <div>
          <label className="block text-sm text-[#45454a] mb-2">背景图片</label>
          <input
            type="file"
            accept="image/*"
            onChange={handleImageChange}
            className="text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
          />
        </div>
        <div className="flex gap-2">
          {imageUrl && (
            <button
              onClick={clearBackground}
              className="px-3 py-2 text-sm text-[#45454a] bg-gray-100/80 rounded hover:bg-gray-200/80"
            >
              清除背景图片
            </button>
          )}
          <button
            onClick={restoreDefaults}
            className="px-3 py-2 text-sm text-[#45454a] bg-gray-100/80 rounded hover:bg-gray-200/80"
          >
            恢复默认设置
          </button>
        </div>
      </div>
    </div>
  )
}

export function Sidebar() {
  return (
    <div className="space-y-4 rounded-lg overflow-hidden">
      <div className="bg-white/85 backdrop-blur-sm rounded-lg p-4 shadow-sm border border-black border-opacity-50">
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
          每日 UTC 00:20 更新。温馨提示: arXiv 假日不更新。 <br /><br />
          欢迎赞助 LLM API，目前需要 rate limit 较高的 api... <br /><br />
        </p>
      </div>
      <BackgroundSettings />
    </div>
  )
}

