import React, { useState, useEffect, useRef } from 'react';
import {
  SafeAreaView,
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';

const App = () => {
  // State for messages and the current input value
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const flatListRef = useRef(null);

  // Set the initial welcome message
  useEffect(() => {
    setMessages([
      {
        id: '1',
        text: 'Hello! Ask me a question about the scriptures or conference talks.',
        sender: 'bot',
      },
    ]);
  }, []);

  const handleSendMessage = () => {
    if (inputValue.trim() === '' || isLoading) return;

    // Add user's message to the chat
    const userMessage = {
      id: Math.random().toString(36).substring(7),
      text: inputValue,
      sender: 'user',
    };
    setMessages(prevMessages => [...prevMessages, userMessage]);
    setInputValue('');
    setIsLoading(true);

    // The ip address when running flask in WSL and app is an emulator. Will need to be different when running on physical device or not on same machine, currently points to localhost for running flask in WSL environment
    fetch('http://10.0.2.2:5000/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message: userMessage.text }),
    })
      .then(response => response.json())
      .then(data => {
        if (data.reply) {
          const botMessage = {
            id: Math.random().toString(36).substring(7),
            text: data.reply,
            sender: 'bot',
          };
          setMessages(prevMessages => [...prevMessages, botMessage]);
        } else {
          console.error("No reply in response data:", data);
          const errorMessage = {
            id: Math.random().toString(36).substring(7),
            text: 'Sorry, I received an unexpected response from the server.',
            sender: 'bot',
          };
          setMessages(prevMessages => [...prevMessages, errorMessage]);
        }
      })
      .catch(error => {
        console.error('Error fetching from server:', error);
        const errorMessage = {
            id: Math.random().toString(36).substring(7),
            text: 'Sorry, I am having trouble connecting to the server.',
            sender: 'bot',
        };
        setMessages(prevMessages => [...prevMessages, errorMessage]);
      })
      .finally(() => {
          setIsLoading(false);
      });
  };
  
  // Renders each message bubble
  const renderMessage = ({ item }) => (
    <View style={[
      styles.messageContainer,
      item.sender === 'user' ? styles.userMessageContainer : styles.botMessageContainer
    ]}>
      <Text style={item.sender === 'user' ? styles.userMessageText : styles.botMessageText}>
        {item.text}
      </Text>
    </View>
  );

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Digital Liahona</Text>
      </View>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={styles.container}
        keyboardVerticalOffset={Platform.OS === "ios" ? 60 : 0}
      >
        <FlatList
          ref={flatListRef}
          data={messages}
          renderItem={renderMessage}
          keyExtractor={item => item.id}
          style={styles.messageList}
          contentContainerStyle={{ paddingVertical: 10 }}
          onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
          onLayout={() => flatListRef.current?.scrollToEnd({ animated: true })}
        />
        {isLoading && (
            <View style={styles.typingIndicatorContainer}>
                <ActivityIndicator size="small" color="#999" />
            </View>
        )}
        <View style={styles.inputContainer}>
          <TextInput
            style={styles.input}
            value={inputValue}
            onChangeText={setInputValue}
            placeholder="Type your message..."
            placeholderTextColor="#999"
            editable={!isLoading}
          />
          <TouchableOpacity 
            style={[styles.sendButton, isLoading && styles.sendButtonDisabled]} 
            onPress={handleSendMessage}
            disabled={isLoading}>
            <Text style={styles.sendButtonText}>Send</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
};

// --- Styles ---
const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: '#fff' },
  container: { flex: 1, backgroundColor: '#f0f0f0' },
  header: {
    backgroundColor: '#007AFF', // A standard iOS blue
    paddingVertical: 15,
    paddingHorizontal: 10,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#ddd',
  },
  headerTitle: { color: '#fff', fontSize: 17, fontWeight: '600' },
  messageList: { flex: 1, paddingHorizontal: 10, },
  messageContainer: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 20,
    marginBottom: 8,
    maxWidth: '80%',
  },
  userMessageContainer: {
    backgroundColor: '#007AFF',
    alignSelf: 'flex-end',
  },
  botMessageContainer: {
    backgroundColor: '#E5E5EA',
    alignSelf: 'flex-start',
  },
  userMessageText: { color: '#fff', fontSize: 16 },
  botMessageText: { color: '#000', fontSize: 16 },
  typingIndicatorContainer: {
    padding: 10,
    alignItems: 'flex-start',
    marginLeft: 10,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 10,
    borderTopWidth: 1,
    borderTopColor: '#ddd',
    backgroundColor: '#fff',
  },
  input: {
    flex: 1,
    height: 40,
    backgroundColor: '#f0f0f0',
    borderRadius: 20,
    paddingHorizontal: 15,
    fontSize: 16,
  },
  sendButton: {
    marginLeft: 10,
    paddingHorizontal: 15,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#007AFF',
    borderRadius: 20,
  },
  sendButtonDisabled: { backgroundColor: '#B0C4DE' },
  sendButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
});

export default App;
