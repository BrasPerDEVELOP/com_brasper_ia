function deriveBaseUrl(apiUrl) {
  if (apiUrl.endsWith('/consulta-webchat')) {
    return apiUrl.slice(0, -'/consulta-webchat'.length);
  }
  return apiUrl.replace(/\/$/, '');
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  return response.json();
}

export async function sendChatMessage(apiUrl, message) {
  const data = await postJson(apiUrl, { message });
  if (!data || typeof data.response !== 'string') {
    throw new Error('Invalid chat response payload');
  }

  return data.response;
}

export async function startSession(apiUrl, sessionId) {
  const data = await postJson(`${deriveBaseUrl(apiUrl)}/webchat/session/start`, {
    session_id: sessionId || null,
  });
  if (!data || typeof data.session_id !== 'string') {
    throw new Error('Invalid webchat start payload');
  }
  return data;
}

export async function sendSessionMessage(apiUrl, sessionId, message) {
  const data = await postJson(`${deriveBaseUrl(apiUrl)}/webchat/session/message`, {
    session_id: sessionId,
    message,
  });
  if (!data || typeof data.session_id !== 'string') {
    throw new Error('Invalid webchat message payload');
  }
  return data;
}
