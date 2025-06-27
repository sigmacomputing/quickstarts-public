// public/assets/impersonate.js
// This script handles user impersonation for Sigma embeds by fetching the embed URL based on the selected user.

const memberIdMap = {
  admin: "", // will be filled in dynamically
  build: "",
  view: "",
};

// Fetch these from the server before usage
async function loadMemberIds() {
  const res = await fetch("/member-ids");
  const data = await res.json();
  Object.assign(memberIdMap, data);
}

// This function is called when the user selects a role from the dropdown
async function loadEmbed() {
  const roleKey = document.getElementById("userSelect").value;
  const memberId = memberIdMap[roleKey];

  if (!memberId) {
    alert("Invalid or missing memberId for selected role.");
    return;
  }

  try {
    const res = await fetch(`/embed-url?memberId=${memberId}`);
    const data = await res.json();

    // Check if the response contains a valid path
    const iframe = document.getElementById("sigma-embed");
    iframe.src = `https://app.sigmacomputing.com${data.path}`;
  } catch (err) {
    console.error("Error loading embed:", err);
    document.getElementById("sigma-embed").outerHTML =
      '<p style="color:red;">Failed to load Sigma embed.</p>';
  }
}

// Attach the loadEmbed function to the button click event
window.addEventListener("DOMContentLoaded", loadMemberIds);
