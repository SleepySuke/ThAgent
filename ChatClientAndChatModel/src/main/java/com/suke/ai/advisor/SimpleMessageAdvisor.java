package com.suke.ai.advisor;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClientRequest;
import org.springframework.ai.chat.client.ChatClientResponse;
import org.springframework.ai.chat.client.advisor.api.AdvisorChain;
import org.springframework.ai.chat.client.advisor.api.BaseAdvisor;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.metadata.ChatGenerationMetadata;
import org.springframework.ai.chat.prompt.Prompt;

import java.util.*;

/**
 * @author 自然醒
 * @version 1.0
 */
@Slf4j
public class SimpleMessageAdvisor implements BaseAdvisor {

    //存储的消息列表
    private static Map<String, List<Message>> messageList = new HashMap<>();

    @Override
    public ChatClientRequest before(ChatClientRequest chatClientRequest, AdvisorChain advisorChain) {
        log.info("请求之前的消息 - >{}", chatClientRequest);

        String id = chatClientRequest.context().get("id").toString();

        //通过用户id进行查询之前的对话
//        String id = "111";
        List<Message> messages = messageList.get(id);
        //如果之前没有对话，则是新对话，直接存储
        if(messages == null){
            messages = new ArrayList<>();
        }
        //存在上次对话，将这次新对话进行拼接存储
        List<Message> instructions = chatClientRequest.prompt().getInstructions();
        messages.addAll(instructions);
        //对话拼接之后，更新这次请求对话内容
        Prompt oldPrompt = chatClientRequest.prompt();
        Prompt newPrompt = oldPrompt.mutate().messages(messages).build();
        ChatClientRequest clientRequest = chatClientRequest.mutate().prompt(newPrompt).build();
        //拿到新请求之后，需要将本次的对话再次进行存储
        messageList.put(id, messages);
        return clientRequest;
    }

    @Override
    public ChatClientResponse after(ChatClientResponse chatClientResponse, AdvisorChain advisorChain) {

        String id = chatClientResponse.context().get("id").toString();

//        String id = "111";
        List<Message> historyMsg = messageList.get(id);

        if(historyMsg == null){
            historyMsg = new ArrayList<>();
        }

        if(Objects.isNull(chatClientResponse)){
            return chatClientResponse;
        }
//        ChatGenerationMetadata metadata = chatClientResponse.chatResponse().getResult().getMetadata();
        AssistantMessage output = chatClientResponse.chatResponse().getResult().getOutput();
        historyMsg.add(output);
        messageList.put(id, historyMsg);
        log.info("响应之后的消息 - >{}", chatClientResponse);
        return chatClientResponse;
    }

    @Override
    public int getOrder() {
        return 0;
    }
}
