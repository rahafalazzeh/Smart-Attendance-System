function togglePassword() {
    const password = document.getElementById("password");

    if (password) {
        password.type = password.type === "password" ? "text" : "password";
    }
}

function toggleSidebar() {
    const sidebar = document.querySelector(".sidebar");

    if (sidebar) {
        sidebar.classList.toggle("closed");
    }
}