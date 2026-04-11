export async function sendChatMessage(apiUrl, message) {
  const response = await fetch(apiUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message }),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const data = await response.json();
  if (!data || typeof data.response !== 'string') {
    throw new Error('Invalid chat response payload');
  }

  return data.response;
}
