(() => {

    const app = document.getElementById("app");

    const menu = document.getElementById("menuToggle");

    if (app && menu) {

        // Start with sidebar closed

        app.classList.add("sidebar-collapsed");

        menu.addEventListener("click", () => {

            app.classList.toggle("sidebar-collapsed");

        });

    }

    const bell = document.getElementById("notificationBell");

    const dropdown = document.getElementById("notificationDropdown");

    const list = document.getElementById("notificationList");

    const count = document.getElementById("notificationCount");

    if (!bell || !dropdown || !list) return;

    function setCount(n) {

        if (count) {

            count.textContent = String(n);

            count.hidden = n === 0;

        }

    }

    async function refresh() {

        try {

            const response = await fetch("/api/notifications");

            if (!response.ok) {

                throw new Error("Unable to fetch notifications");

            }

            const items = await response.json();

            setCount(items.length);

            list.replaceChildren();

            if (!items.length) {

                const empty = document.createElement("div");

                empty.className = "notification-empty";

                empty.textContent = "No new notifications";

                list.append(empty);

                return;

            }

            for (const item of items) {

                const el = document.createElement("div");

                el.className = "notification-item";

                const priority = document.createElement("span");

priority.className =

    "priority " + (item.priority || "Low").toLowerCase();

priority.textContent = item.priority || "Low";

const client = document.createElement("strong");

client.className = "notification-client";

client.textContent =

    item.client_name || "Unknown client";

const message = document.createElement("p");

message.className = "notification-action";

message.textContent = item.message;

const time = document.createElement("small");

time.textContent = item.created_at + " MYT";

const button = document.createElement("button");

button.type = "button";

button.className = "notification-read-button";

button.textContent = "Mark as read";

el.append(priority, client, message, time, button);

button.addEventListener("click", async () => {

    try {

        const res = await fetch(

            "/api/notifications/" + item.id + "/read",

            { method: "POST" }

        );

        if (!res.ok) {

            throw new Error("Could not mark as read");

        }

        el.remove();

        setCount(

            list.querySelectorAll(

                ".notification-item"

            ).length

        );

        if (!list.querySelector(".notification-item")) {

            list.textContent = "No new notifications";

        }

    } catch (err) {

        alert(err.message);

    }

});

                list.append(el);

            }

        } catch (err) {

            list.textContent = "Unable to load notifications";

            console.error(err);

        }

    }

    bell.addEventListener("click", () => {

        dropdown.hidden = !dropdown.hidden;

        bell.setAttribute(

            "aria-expanded",

            String(!dropdown.hidden)

        );

        if (!dropdown.hidden) {

            refresh();

        }

    });

    document.addEventListener("click", (event) => {

        if (!event.target.closest("#notificationWrapper")) {

            dropdown.hidden = true;

            bell.setAttribute("aria-expanded", "false");

        }

    });

})();