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
  Linking,
  Alert,
  ScrollView,
} from 'react-native';

const App = () => {
  // State for messages and the current input value
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedChapter, setSelectedChapter] = useState(null);
  const [selectedTopic, setSelectedTopic] = useState(null);
  const [selectedTalk, setSelectedTalk] = useState(null);
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
            relatedContent: data.related_content || null,
            versesWithLinks: data.verses_with_links || null,
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

  const handleChapterLink = async (chapterUrl) => {
    try {
      // Extract book and chapter from URL
      const urlParts = chapterUrl.split('/');
      const book = urlParts[urlParts.length - 2];
      const chapter = urlParts[urlParts.length - 1];
      
      // Fetch chapter content
      const response = await fetch(`http://10.0.2.2:5000/chapter/${book}/${chapter}`);
      if (response.ok) {
        const chapterData = await response.json();
        setSelectedChapter(chapterData);
      } else {
        Alert.alert('Error', 'Could not load chapter content.');
      }
    } catch (error) {
      console.error('Error fetching chapter:', error);
      Alert.alert('Error', 'Could not load chapter content.');
    }
  };

  const handleTopicLink = async (topicUrl) => {
    try {
      // Extract topic name from URL
      const topicName = topicUrl.split('/').pop();
      
      // Fetch topic content
      const response = await fetch(`http://10.0.2.2:5000/topic/${topicName}`);
      if (response.ok) {
        const topicData = await response.json();
        setSelectedTopic(topicData);
      } else {
        Alert.alert('Error', 'Could not load topic content.');
      }
    } catch (error) {
      console.error('Error fetching topic:', error);
      Alert.alert('Error', 'Could not load topic content.');
    }
  };

  const handleTalkLink = async (talkTitle) => {
    try {
      const response = await fetch(`http://10.0.2.2:5000/talk/${encodeURIComponent(talkTitle)}`);
      if (response.ok) {
        const talkData = await response.json();
        setSelectedTalk(talkData);
      } else {
        Alert.alert('Error', 'Could not load talk content.');
      }
    } catch (error) {
      Alert.alert('Error', 'Could not load talk content.');
    }
  };

  const parseMessageWithLinks = (text) => {
    // For now, just return the text as-is to avoid complex parsing issues
    return text;
  };

  const renderMessageWithExplanations = (text) => {
    // Split the text into sections and render explanations with special styling
    const lines = text.split('\n');
    const textComponents = lines.map((line, index) => {
      const trimmedLine = line.trim();
      
      if (trimmedLine.startsWith('💡')) {
        // This is an explanation line
        return (
          <Text key={index} style={styles.explanationText}>
            {line}
          </Text>
        );
      } else if (trimmedLine.startsWith('**') && trimmedLine.includes('**')) {
        // This is a numbered item (e.g., "**1.** From...")
        return (
          <Text key={index} style={styles.numberedItemText}>
            {line}
          </Text>
        );
      } else if (trimmedLine.startsWith('📖') || trimmedLine.startsWith('🎤') || trimmedLine.startsWith('🔗') || trimmedLine.startsWith('📚')) {
        // This is a section header
        return (
          <Text key={index} style={styles.sectionHeaderText}>
            {line}
          </Text>
        );
      } else if (trimmedLine.startsWith('   "') && trimmedLine.endsWith('"')) {
        // This is a quoted text line (indented)
        return (
          <Text key={index} style={styles.quotedText}>
            {line}
          </Text>
        );
      } else if (trimmedLine.startsWith('•')) {
        // This is a bullet point
        return (
          <Text key={index} style={styles.bulletPointText}>
            {line}
          </Text>
        );
      } else if (trimmedLine === '') {
        // Empty line for spacing
        return <View key={index} style={styles.spacingView} />;
      } else {
        // Regular text
        return (
          <Text key={index} style={styles.regularText}>
            {line}
          </Text>
        );
      }
    });
    
    // Return a View container that holds all the text components
    return (
      <View style={styles.messageTextContainer}>
        {textComponents}
      </View>
    );
  };

  const renderRelatedContent = (relatedContent) => {
    if (!relatedContent) return null;

    return (
      <View style={styles.relatedContentContainer}>
        {relatedContent.related_topics && relatedContent.related_topics.length > 0 && (
          <View style={styles.relatedSection}>
            <Text style={styles.relatedSectionTitle}>📚 Related Topics</Text>
            {relatedContent.related_topics.map((topic, index) => (
              <View key={index} style={styles.relatedItem}>
                <Text style={styles.relatedItemText}>
                  • {topic.name} ({topic.verse_count} verses, {topic.talk_count} talks)
                </Text>
                <TouchableOpacity onPress={() => handleTopicLink(topic.topic_url)}>
                  <Text style={styles.linkText}>Explore</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}

        {relatedContent.related_verses && relatedContent.related_verses.length > 0 && (
          <View style={styles.relatedSection}>
            <Text style={styles.relatedSectionTitle}>📖 Additional Scripture References</Text>
            {relatedContent.related_verses.map((verse, index) => (
              <TouchableOpacity
                key={index}
                style={styles.relatedItem}
                onPress={() => verse.chapter_info && handleChapterLink(verse.chapter_info.chapter_url)}
              >
                <Text style={styles.relatedItemText}>
                  • {verse.source}: "{verse.text.substring(0, 100)}..."
                </Text>
                {verse.chapter_info && (
                  <Text style={styles.linkText}>Read Chapter</Text>
                )}
              </TouchableOpacity>
            ))}
          </View>
        )}

        {relatedContent.related_talks && relatedContent.related_talks.length > 0 && (
          <View style={styles.relatedSection}>
            <Text style={styles.relatedSectionTitle}>🎤 Related Conference Talks</Text>
            {relatedContent.related_talks.map((talk, index) => (
              <TouchableOpacity
                key={index}
                style={styles.relatedItem}
                onPress={() => handleTalkLink(talk.source)}
              >
                <Text style={styles.relatedItemText}>
                  • {talk.source} ({talk.year}): "{talk.text.substring(0, 100)}..."
                </Text>
                <Text style={styles.linkText}>Read Full Talk</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}
      </View>
    );
  };

  const renderChapterModal = () => {
    if (!selectedChapter) return null;

    return (
      <View style={styles.modalOverlay}>
        <View style={styles.modalContent}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>
              {selectedChapter.book_title} {selectedChapter.chapter_number}
            </Text>
            <TouchableOpacity
              style={styles.closeButton}
              onPress={() => setSelectedChapter(null)}
            >
              <Text style={styles.closeButtonText}>✕</Text>
            </TouchableOpacity>
          </View>
          
          {selectedChapter.summary && (
            <Text style={styles.chapterSummary}>{selectedChapter.summary}</Text>
          )}
          
          <ScrollView style={styles.chapterVerses}>
            {selectedChapter.verses.map((verse, index) => (
              <View key={index} style={styles.verseContainer}>
                <Text style={styles.verseNumber}>{verse.number}.</Text>
                <Text style={styles.verseText}>{verse.text}</Text>
              </View>
            ))}
          </ScrollView>
        </View>
      </View>
    );
  };

  const renderTopicModal = () => {
    if (!selectedTopic) return null;

    return (
      <View style={styles.modalOverlay}>
        <View style={styles.modalContent}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>{selectedTopic.topic_name}</Text>
            <TouchableOpacity
              style={styles.closeButton}
              onPress={() => setSelectedTopic(null)}
            >
              <Text style={styles.closeButtonText}>✕</Text>
            </TouchableOpacity>
          </View>
          
          <Text style={styles.topicStats}>
            {selectedTopic.verse_count} verses • {selectedTopic.talk_count} talks
          </Text>
          
          <ScrollView style={styles.topicContent}>
            {selectedTopic.verses.length > 0 && (
              <View style={styles.topicSection}>
                <Text style={styles.topicSectionTitle}>Scripture References</Text>
                {selectedTopic.verses.map((verse, index) => (
                  <TouchableOpacity
                    key={index}
                    style={styles.topicVerse}
                    onPress={() => handleChapterLink(verse.chapter_info.chapter_url)}
                  >
                    <Text style={styles.topicVerseSource}>{verse.source}</Text>
                    <Text style={styles.topicVerseText}>{verse.text}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}
            
            {selectedTopic.talks.length > 0 && (
              <View style={styles.topicSection}>
                <Text style={styles.topicSectionTitle}>Conference Talks</Text>
                {selectedTopic.talks.map((talk, index) => (
                  <View key={index} style={styles.topicTalk}>
                    <Text style={styles.topicTalkTitle}>{talk.title}</Text>
                    <Text style={styles.topicTalkYear}>{talk.year} • {talk.season}</Text>
                  </View>
                ))}
              </View>
            )}
          </ScrollView>
        </View>
      </View>
    );
  };

  const renderTalkModal = () => {
    if (!selectedTalk) return null;
    return (
      <View style={styles.modalOverlay}>
        <View style={styles.modalContent}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>{selectedTalk.title}</Text>
            <TouchableOpacity
              style={styles.closeButton}
              onPress={() => setSelectedTalk(null)}
            >
              <Text style={styles.closeButtonText}>✕</Text>
            </TouchableOpacity>
          </View>
          <Text style={styles.topicStats}>
            {selectedTalk.year} • {selectedTalk.season}
          </Text>
          <ScrollView style={styles.talkParagraphs}>
            {selectedTalk.paragraphs.map((para, idx) => (
              <Text key={idx} style={styles.talkParagraphText}>
                {para}
              </Text>
            ))}
          </ScrollView>
        </View>
      </View>
    );
  };

  // Renders each message bubble
  const renderMessage = ({ item }) => (
    <View style={[
      styles.messageContainer,
      item.sender === 'user' ? styles.userMessageContainer : styles.botMessageContainer
    ]}>
      {item.sender === 'user' ? (
        <Text style={styles.userMessageText}>
          {item.text}
        </Text>
      ) : (
        renderMessageWithExplanations(item.text)
      )}
      {item.sender === 'bot' && item.relatedContent && renderRelatedContent(item.relatedContent)}
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
      
      {/* Modals */}
      {renderChapterModal()}
      {renderTopicModal()}
      {renderTalkModal()}
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
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 20,
    marginBottom: 12,
    maxWidth: '85%',
  },
  userMessageContainer: {
    backgroundColor: '#007AFF',
    alignSelf: 'flex-end',
  },
  botMessageContainer: {
    backgroundColor: '#E5E5EA',
    alignSelf: 'flex-start',
  },
  userMessageText: { 
    color: '#fff', 
    fontSize: 16,
    lineHeight: 22,
  },
  botMessageText: { 
    color: '#000', 
    fontSize: 16,
    lineHeight: 22,
  },
  linkText: { 
    color: '#007AFF', 
    textDecorationLine: 'underline',
    fontWeight: '500',
  },
  relatedContentContainer: {
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#ddd',
  },
  relatedSection: {
    marginBottom: 16,
  },
  relatedSectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 8,
    color: '#333',
    lineHeight: 22,
  },
  relatedItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
  },
  relatedItemText: {
    fontSize: 14,
    color: '#333',
    flex: 1,
    lineHeight: 20,
  },
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
  // Modal styles
  modalOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 1000,
  },
  modalContent: {
    backgroundColor: '#fff',
    borderRadius: 10,
    margin: 20,
    maxHeight: '80%',
    width: '90%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 15,
    borderBottomWidth: 1,
    borderBottomColor: '#ddd',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
    flex: 1,
  },
  closeButton: {
    padding: 5,
  },
  closeButtonText: {
    fontSize: 20,
    color: '#999',
  },
  chapterSummary: {
    padding: 15,
    fontSize: 14,
    color: '#666',
    fontStyle: 'italic',
    backgroundColor: '#f9f9f9',
    lineHeight: 20,
  },
  chapterVerses: {
    padding: 15,
  },
  verseContainer: {
    flexDirection: 'row',
    marginBottom: 12,
  },
  verseNumber: {
    fontSize: 14,
    fontWeight: '600',
    color: '#007AFF',
    marginRight: 8,
    minWidth: 30,
  },
  verseText: {
    fontSize: 14,
    color: '#333',
    flex: 1,
    lineHeight: 20,
  },
  topicStats: {
    padding: 15,
    fontSize: 14,
    color: '#666',
    backgroundColor: '#f9f9f9',
    lineHeight: 20,
  },
  topicContent: {
    padding: 15,
  },
  topicSection: {
    marginBottom: 20,
  },
  topicSectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 10,
    color: '#333',
    lineHeight: 22,
  },
  topicVerse: {
    marginBottom: 10,
    padding: 10,
    backgroundColor: '#f9f9f9',
    borderRadius: 5,
  },
  topicVerseSource: {
    fontSize: 12,
    fontWeight: '600',
    color: '#007AFF',
    marginBottom: 5,
  },
  topicVerseText: {
    fontSize: 14,
    color: '#333',
    lineHeight: 18,
  },
  topicTalk: {
    marginBottom: 10,
    padding: 10,
    backgroundColor: '#f9f9f9',
    borderRadius: 5,
  },
  topicTalkTitle: {
    fontSize: 14,
    fontWeight: '500',
    color: '#333',
    marginBottom: 3,
  },
  topicTalkYear: {
    fontSize: 12,
    color: '#666',
  },
  explanationText: {
    fontSize: 14,
    color: '#666',
    fontStyle: 'italic',
    lineHeight: 20,
    marginTop: 4,
  },
  numberedItemText: {
    fontSize: 15,
    color: '#333',
    fontWeight: '600',
    lineHeight: 22,
    marginTop: 8,
  },
  quotedText: {
    fontSize: 14,
    color: '#333',
    fontStyle: 'italic',
    lineHeight: 20,
    marginLeft: 16,
    marginTop: 4,
  },
  bulletPointText: {
    fontSize: 14,
    color: '#333',
    fontWeight: '500',
    lineHeight: 20,
    marginTop: 4,
  },
  spacingView: {
    height: 8,
    width: '100%',
  },
  sectionHeaderText: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 8,
    color: '#333',
    lineHeight: 22,
    marginTop: 12,
  },
  regularText: {
    fontSize: 14,
    color: '#333',
    lineHeight: 20,
  },
  messageTextContainer: {
    marginVertical: 2,
  },
  talkParagraphs: {
    padding: 15,
  },
  talkParagraphText: {
    fontSize: 15,
    color: '#333',
    marginBottom: 12,
    lineHeight: 22,
  },
});

export default App;
