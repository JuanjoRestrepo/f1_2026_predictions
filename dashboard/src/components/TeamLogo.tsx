import React from "react";

interface TeamLogoProps {
  team: string;
  size?: number;
  className?: string;
}

export function TeamLogo({ team, size = 20, className = "" }: TeamLogoProps): React.JSX.Element {
  const normalized = (team || "").trim().toLowerCase();

  // McLaren: Papaya speedmark / aerodynamic swoosh
  if (normalized.includes("mclaren")) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`inline-block flex-shrink-0 ${className}`}
        aria-label="McLaren"
      >
        <path
          d="M6 22C11 15 22 10 26 10C22 13 14 17 9 22H6Z"
          fill="#FF8000"
        />
        <path
          d="M10 21C16 15 23 11 26 10C21.5 13.5 15.5 17.5 12 21H10Z"
          fill="#FF8000"
        />
      </svg>
    );
  }

  // Ferrari: Prancing horse emblem / yellow shield & black stallion silhouette
  if (normalized.includes("ferrari")) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`inline-block flex-shrink-0 ${className}`}
        aria-label="Ferrari"
      >
        <rect x="7" y="4" width="18" height="24" rx="3" fill="#FFF200" />
        <path
          d="M7 4H25V6H7V4Z"
          fill="#009246"
        />
        <path
          d="M7 6H25V8H7V6Z"
          fill="#FFFFFF"
        />
        <path
          d="M7 8H25V10H7V8Z"
          fill="#CE2B37"
        />
        {/* Stylized prancing horse silhouette */}
        <path
          d="M18.5 11C18 11.5 17 12 16.5 12C15.8 12 15.5 11.2 15 11.5C14.5 11.8 14.8 13 14.2 13.5C13.6 14 13 14.2 13 15C13.8 15.2 14.5 14.8 15 15.5C15.5 16.2 15 17.5 14.5 18.5C14 19.5 13.2 20.2 13.5 21C14 21 14.5 20.2 15 19.5C15.5 18.8 16 18.2 16.8 18.8C17.2 19.2 17 20.5 17.5 21.5C18 22.5 18.5 23.5 19 24C19.2 23 18.8 21.5 18.5 20.5C18.2 19.5 18.5 18.5 18.2 17.5C18 16.5 17.2 16 17.5 15C17.8 14 18.8 13.8 19 12.8C19.2 11.8 19 11.2 18.5 11Z"
          fill="#111111"
        />
      </svg>
    );
  }

  // Mercedes: Three-pointed star in a circle
  if (normalized.includes("mercedes")) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`inline-block flex-shrink-0 ${className}`}
        aria-label="Mercedes"
      >
        <circle cx="16" cy="16" r="13" stroke="#27F4D2" strokeWidth="2" fill="none" />
        <path
          d="M16 4.5L18.5 15.5L16 16.5L13.5 15.5L16 4.5Z"
          fill="#E5E7EB"
        />
        <path
          d="M26.5 22L16 16.5L16.8 15.5L25 19.5L26.5 22Z"
          fill="#E5E7EB"
        />
        <path
          d="M5.5 22L16 16.5L15.2 15.5L7 19.5L5.5 22Z"
          fill="#E5E7EB"
        />
      </svg>
    );
  }

  // Red Bull Racing / Red Bull
  if (normalized.includes("red bull") && !normalized.includes("racing bulls") && !normalized.includes("rb")) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`inline-block flex-shrink-0 ${className}`}
        aria-label="Red Bull Racing"
      >
        <circle cx="16" cy="16" r="10" fill="#EA1D2D" />
        <circle cx="16" cy="16" r="7" fill="#FCD116" />
        <path
          d="M10 17C12 14 15 13 18 13.5C16 14.5 14.5 16 14 18H10Z"
          fill="#EA1D2D"
        />
        <path
          d="M22 17C20 14 17 13 14 13.5C16 14.5 17.5 16 18 18H22Z"
          fill="#001A30"
        />
      </svg>
    );
  }

  // Racing Bulls / RB
  if (normalized.includes("racing bulls") || normalized === "rb" || normalized.includes("vcarb")) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`inline-block flex-shrink-0 ${className}`}
        aria-label="Racing Bulls"
      >
        <circle cx="16" cy="16" r="13" stroke="#6692FF" strokeWidth="2" fill="#0A1128" />
        <path
          d="M10 20C12 16 16 14 20 14C17.5 15.5 15.5 17.5 15 20H10Z"
          fill="#E5E7EB"
        />
        <path
          d="M22 20C20 16 16 14 12 14C14.5 15.5 16.5 17.5 17 20H22Z"
          fill="#6692FF"
        />
      </svg>
    );
  }

  // Aston Martin / Aston Martin Aramco
  if (normalized.includes("aston martin")) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`inline-block flex-shrink-0 ${className}`}
        aria-label="Aston Martin"
      >
        <path
          d="M4 14C8 14 12 16 16 19C20 16 24 14 28 14C23 18 19 20 16 20C13 20 9 18 4 14Z"
          fill="#006F62"
        />
        <path
          d="M6 15C10 15 13 17 16 19C19 17 22 15 26 15C22 17 19 18.5 16 18.5C13 18.5 10 17 6 15Z"
          fill="#CEDC00"
        />
      </svg>
    );
  }

  // Alpine: Alpine stylized 'A' mark
  if (normalized.includes("alpine")) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`inline-block flex-shrink-0 ${className}`}
        aria-label="Alpine"
      >
        <path
          d="M16 6L7 24H12.5L14.5 20H18L16 16L18 12L20.5 17H25L16 6Z"
          fill="#0093CC"
        />
        <path
          d="M18 20L21 24H26L22.5 19L18 20Z"
          fill="#FF87BC"
        />
      </svg>
    );
  }

  // Williams: Williams iconic 'W'
  if (normalized.includes("williams")) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`inline-block flex-shrink-0 ${className}`}
        aria-label="Williams"
      >
        <path
          d="M6 9H10.5L14 19L17.5 9H20L16 23H13L9.5 13L6.5 23H4L6 9Z"
          fill="#005AFF"
        />
        <path
          d="M20 9H23.5L27 20L25 23L21.5 12.5L19 23H16.5L20 9Z"
          fill="#64C4FF"
        />
      </svg>
    );
  }

  // Haas / Haas F1 Team: Circle-H mark
  if (normalized.includes("haas")) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`inline-block flex-shrink-0 ${className}`}
        aria-label="Haas"
      >
        <circle cx="16" cy="16" r="13" stroke="#B6BABD" strokeWidth="2" fill="none" />
        <path
          d="M11 9H14V14H18V9H21V23H18V17H14V23H11V9Z"
          fill="#E6002B"
        />
      </svg>
    );
  }

  // Sauber / Kick Sauber / Audi
  if (normalized.includes("sauber") || normalized.includes("audi")) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`inline-block flex-shrink-0 ${className}`}
        aria-label="Sauber / Audi"
      >
        <rect x="6" y="6" width="20" height="20" rx="4" fill="#15151E" stroke="#52E252" strokeWidth="2" />
        <path
          d="M11 11H21V15H15V17H21V21H11V11Z"
          fill="#52E252"
        />
      </svg>
    );
  }

  // Cadillac (2026 entry)
  if (normalized.includes("cadillac")) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`inline-block flex-shrink-0 ${className}`}
        aria-label="Cadillac"
      >
        <path
          d="M8 10L16 6L24 10L22 20L16 26L10 20L8 10Z"
          fill="#1C1C1E"
          stroke="#FFD700"
          strokeWidth="2"
        />
        <path
          d="M12 12H20V15H12V12ZM13 17H19V20H13V17Z"
          fill="#FFD700"
        />
      </svg>
    );
  }

  // Default fallback: team color rounded badge
  return (
    <div
      style={{ width: size, height: size }}
      className={`rounded-full bg-zinc-700 border border-white/20 flex items-center justify-center text-[9px] font-bold text-white flex-shrink-0 ${className}`}
    >
      {team.charAt(0).toUpperCase()}
    </div>
  );
}
