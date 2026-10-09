(() => {

    const button = document.getElementById("aiAssistantButton");
    const windowBox = document.getElementById("aiAssistantWindow");
    const closeButton = document.getElementById("aiAssistantClose");
    const form = document.getElementById("aiAssistantForm");
    const input = document.getElementById("aiAssistantInput");
    const messages = document.getElementById("aiAssistantMessages");

    if (
        !button ||
        !windowBox ||
        !closeButton ||
        !form ||
        !input ||
        !messages
    ) {
        return;
    }

    button.addEventListener("click", () => {
        windowBox.hidden = false;
        button.hidden = true;
        input.focus();
    });

    closeButton.addEventListener("click", () => {
        windowBox.hidden = true;
        button.hidden = false;
    });

    function addMessage(text, type) {
        const message = document.createElement("div");
        message.className = type === "user"
            ? "user-message"
            : "ai-message";

        if (type === "ai") {
            const title = document.createElement("strong");
            title.textContent = "✨ AlertIQ";
            message.appendChild(title);
        }

        const paragraph = document.createElement("p");
        paragraph.textContent = text;
        paragraph.style.whiteSpace = "pre-line";
        message.appendChild(paragraph);
        messages.appendChild(message);
        messages.scrollTop = messages.scrollHeight;

        return message;
    }

    form.addEventListener("submit", async (event) => {

        event.preventDefault();

        const question = input.value.trim();

        if (!question) {
            return;
        }

        addMessage(question, "user");

        input.value = "";
        input.disabled = true;

        const thinking = addMessage(
            "Thinking...",
            "ai"
        );

        try {

            const response = await fetch("/api/assistant", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    question: question
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data.answer || "Unable to get a response."
                );
            }

            thinking.querySelector("p").textContent =
                data.answer;

        } catch (error) {

            thinking.querySelector("p").textContent =
                "Sorry, I couldn't process that request.";

            console.error(error);

        } finally {

            input.disabled = false;
            input.focus();
            messages.scrollTop = messages.scrollHeight;

        }

    });

})();