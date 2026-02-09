package com.suke.ai.repository;

import com.suke.ai.mapper.ContentMapper;
import com.suke.ai.pojo.Content;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.memory.ChatMemoryRepository;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.MessageType;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * @author 自然醒
 * @version 1.0
 * @date 2026-02-09 14:39
 * @description 使用数据库对重要对话进行持久化存储
 */
@Slf4j
@Component
public class DBChatMemoryRepository implements ChatMemoryRepository {

    //操作数据库的mapper映射使用注入即可
    @Autowired
    private ContentMapper contentMapper;

    @Override
    @Transactional(readOnly = true)
    public List<String> findConversationIds() {
        return contentMapper.findConversationIds();
    }

    @Override
    @Transactional(readOnly = true)
    public List<Message> findByConversationId(String conversationId) {
        conversationId = generateConversationId();
        log.info("查询的conversationId: {}",conversationId);
        //todo 然后去比较截取当前的用户id去比较 相同则去搜索这次对话 不相同的情况则是一个新用户 新对话
        String tempId = conversationId.substring(0,conversationId.indexOf("_"));
        if(!tempId.equals(getUerId())){
            //todo 不同用户则去数据库中查询
            return List.of();
        }
        List<Content> contents = contentMapper.findByConversationId(conversationId);
        //不存在对话内容，此时对话返回为空，AI模型直接开启一次新对话
        if(contents == null || contents.isEmpty()){
            return List.of();
        }
        List<Message> messages = new ArrayList<>();
        for (Content content : contents) {
            //将上一次用户的内容封装起来 上一次AI的回复内容封装起来
            if(content != null && content.getUserContent() != null && !content.getUserContent().isEmpty()){
                messages.add(new UserMessage(content.getUserContent()));
            }
            if(content != null && content.getAssistantContent() != null && !content.getAssistantContent().isEmpty()){
                messages.add(new AssistantMessage(content.getAssistantContent()));
            }
        }
        return messages;
    }

    @Override
    @Transactional
    public void saveAll(String conversationId, List<Message> messages) {
        //todo 文章的id应该为当前的用户加时间戳
        //todo 目前我这里的userId写死了
        conversationId = generateConversationId();
        if(messages == null || messages.isEmpty()){
            log.warn("并没有发生对话，无需保存");
            return;
        }
        String userContent = null;
        String assistantContent = null;
        Content content = new Content();
        for (Message message : messages) {
            MessageType messageType = message.getMessageType();
            switch (messageType){
                case USER:
                    userContent = message.getText();
                    break;
                case ASSISTANT:
                    assistantContent = message.getText();
                    if(userContent != null && assistantContent != null){
                        //对话内容是用户于AI回复成对出现的
                        content.setUserContent(userContent);
                        content.setAssistantContent(assistantContent);
                        saveContent(conversationId,userContent,assistantContent);
                        userContent = null;
                        assistantContent = null;
                    }
                    break;
            }
        }
        if(userContent != null){
            //用户发送了内容，但是没有AI回复，此时将用户内容保存起来
            saveContent(conversationId,userContent,"");
        }
    }

    private String getUerId(){
        //todo 获取用户id
        return "1";
    }

    private String generateConversationId(){
        return getUerId() + "_" + System.currentTimeMillis();
    }

    private void saveContent(String conversationId, String userContent, String assistantContent){
        Content content = new Content();
        content.setConversationId(conversationId);
        content.setUserContent(userContent);
        content.setAssistantContent(assistantContent);
        content.setCreateTime(LocalDateTime.now());
        content.setUpdateTime(LocalDateTime.now());
        contentMapper.insert(content);

    }

    @Override
    @Transactional
    public void deleteByConversationId(String conversationId) {
        //todo 其实如果对话过多可以设置一个时间直接将对话内容清除，减轻数据库压力，或是直接像规定上下文窗口一样，当超出某个阈值时可以进行一个分表存储另一段对话内容
        //删除对话
        contentMapper.deleteByConversationId(conversationId);
    }
}
