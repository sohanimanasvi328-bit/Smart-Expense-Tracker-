document.addEventListener('DOMContentLoaded', () => {
    const actionBtn = document.getElementById('action-btn');
    const card = document.getElementById('action-card');

    actionBtn.addEventListener('click', () => {
        // Toggle a simple animation class or change text
        if (actionBtn.textContent === 'Click Me!') {
            actionBtn.textContent = 'Awesome!';
            actionBtn.style.backgroundColor = '#10b981'; // Green color for success

            // Add a little pop effect to the card
            card.style.transform = 'scale(1.02)';
            setTimeout(() => {
                card.style.transform = '';
            }, 200);
        } else {
            actionBtn.textContent = 'Click Me!';
            actionBtn.style.backgroundColor = 'var(--primary-color)';
        }
    });
});
