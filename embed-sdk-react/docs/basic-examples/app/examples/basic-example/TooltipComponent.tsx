// TooltipComponent.tsx
import React from 'react';

interface TooltipProps {
  text: string; // Text to display in the tooltip
  children: React.ReactNode; // The content that triggers the tooltip
}

const TooltipComponent: React.FC<TooltipProps> = ({ text, children }) => (
  <div className="relative group inline-block">
    {/* Trigger Element */}
    {children}
    {/* Tooltip Box */}
    <div
      className="absolute left-1/2 transform -translate-x-1/2 mt-2 px-4 py-2 bg-gray-800 text-white text-sm rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-300 z-50"
      style={{ minWidth: '400px', maxWidth: '600px', pointerEvents: 'none' }}
    >
      {text}
    </div>
  </div>
);

export default TooltipComponent;