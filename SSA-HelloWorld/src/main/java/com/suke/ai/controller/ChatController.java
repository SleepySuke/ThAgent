package com.suke.ai.controller;

import jakarta.annotation.Resource;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

/**
 * @author 自然醒
 * @version 1.0
 */
@RestController
public class ChatController {
    @Resource
    private ChatModel chatModel;

    /**
     * 普通调用
     * 阻塞型
     * @param msg
     * @return
     */
    @GetMapping("/hello/dochat")
    public String doChat(@RequestParam(name = "msg",defaultValue = "请问你是谁")String msg){
        String callBack = chatModel.call( msg);
        return callBack;
    }

    /**
     * 流式型调用
     * @param msg
     * @return
     */
    @GetMapping("/hello/stream")
    public Flux<String> stream(@RequestParam(name = "msg",defaultValue = "请问你是谁")String msg){
        return chatModel.stream(msg);
    }
}
