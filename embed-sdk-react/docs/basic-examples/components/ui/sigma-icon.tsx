function SigmaIcon({ size = 24 }: { size?: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 75 68"
      height={`${size}`}
      width={`${size}`}
    >
      <path
        fill="currentColor"
        d="M51.21 60L22 48h19l10.21 12zM32 35l20.99 24.99L45 22 32 35zM6 9l25 25 13-13L6 9zm49.15 0L45 20l-10-3 20.15-8zm.85 1l-5 6h15l-10-6z"
      ></path>
    </svg>
  );
}

export default SigmaIcon;
