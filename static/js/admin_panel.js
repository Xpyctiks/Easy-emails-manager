// Admin panel: default port hints by the chosen encryption type (IMAP of the new mailbox, SMTP of every mailbox form).

const SMTP_PORTS = { ssl: "465", starttls: "587", none: "25" };

document.addEventListener("DOMContentLoaded", () => {
  const security = document.getElementById("newSecurity");
  const port = document.getElementById("newPort");
  if (security && port) {
    const update = () => { port.placeholder = security.value === "ssl" ? "993" : "143"; };
    security.addEventListener("change", update);
    update();
  }

  document.querySelectorAll(".smtp-security").forEach(select => {
    const smtpPort = select.closest(".row")?.querySelector(".smtp-port");
    if (!smtpPort) return;
    const update = () => { smtpPort.placeholder = SMTP_PORTS[select.value] || ""; };
    select.addEventListener("change", () => {
      // a port that is one of the defaults follows the encryption; a custom port stays
      if (Object.values(SMTP_PORTS).includes(smtpPort.value)) smtpPort.value = SMTP_PORTS[select.value];
      update();
    });
    update();
  });
});
