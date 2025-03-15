'use client'

import { useEffect } from 'react'

const DEFAULT_COLOR = "#fffef7"

export function BackgroundInitializer() {
  useEffect(() => {
    const savedColor = localStorage.getItem("background-color")
    const savedImage = localStorage.getItem("background-image")
    
    if (savedColor) {
      document.body.style.backgroundColor = savedColor
    } else {
      document.body.style.backgroundColor = DEFAULT_COLOR
      localStorage.setItem("background-color", DEFAULT_COLOR)
    }
    
    if (savedImage) {
      document.body.style.backgroundImage = `url(${savedImage})`
      document.body.style.backgroundSize = "cover"
      document.body.style.backgroundPosition = "center"
      document.body.style.backgroundAttachment = "fixed"
    }

    // Add styles for card backgrounds
    document.body.style.setProperty('--card-background', 'rgba(255, 255, 255, 0.85)')
    document.body.style.setProperty('--card-blur', '4px')
  }, [])

  return null
}